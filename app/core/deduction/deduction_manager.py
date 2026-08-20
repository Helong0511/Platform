"""
转化扣减管理逻辑
用于计算扣减和处理优先级

重构说明:
- 使用类封装相关功能,提高代码组织性
- 使用策略模式处理不同的扣减策略
- 添加配置缓存机制提升性能
- 改进错误处理和日志记录
- 增强类型提示
"""
import logging
import hashlib
from typing import Optional, Tuple, Dict, Any, Protocol
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, case, func
from datetime import datetime, timedelta

from app.models.models import (
    ConversionDeductionConfig, 
    ConversionDeductionLog,
)
from app.core.infrastructure.cache_compat import (
    CACHE_PREFIX,
    invalidate_cache,
    legacy_get_cached as get_cached,
    legacy_set_cached as set_cached,
)
from app.core.redis_client import get_redis_client
from app.core.config import settings

logger = logging.getLogger(__name__)

# 缓存配置
CONFIG_CACHE_TTL = 300  # 配置缓存5分钟
CONFIG_CACHE_PREFIX = "cpl:deduction_config:"  # 保留前缀供 invalidate 使用
STATS_CACHE_TTL = 60  # 统计缓存1分钟
STATS_CACHE_PREFIX = "cpl:conversion_stats:"


@dataclass
class ConversionStats:
    """转化统计信息"""
    total: int = 0
    deducted: int = 0
    processed: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'total': self.total,
            'deducted': self.deducted,
            'processed': self.processed
        }


@dataclass
class DeductionResult:
    """扣减结果"""
    should_deduct_volume: bool = False
    should_deduct_amount: bool = False
    original_volume: int = 1
    original_amount: Decimal = Decimal("0")
    final_volume: int = 1
    final_amount: Decimal = Decimal("0")
    deducted_volume: int = 0
    deducted_amount: Decimal = Decimal("0")
    deduction_type: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'should_deduct_volume': self.should_deduct_volume,
            'should_deduct_amount': self.should_deduct_amount,
            'original_volume': self.original_volume,
            'original_amount': self.original_amount,
            'final_volume': self.final_volume,
            'final_amount': self.final_amount,
            'deducted_volume': self.deducted_volume,
            'deducted_amount': self.deducted_amount,
            'deduction_type': self.deduction_type
        }


class DeductionStrategy(ABC):
    """扣减策略抽象基类"""
    
    @abstractmethod
    def should_deduct(
        self,
        config: ConversionDeductionConfig,
        stats: ConversionStats,
        decision_key: str = "",
    ) -> bool:
        """
        判断是否应该扣减当前转化
        
        Args:
            config: 扣减配置
            stats: 转化统计信息
            decision_key: 确定性决策键（如 click_id）
            
        Returns:
            是否应该扣减
        """
        pass


class DeterministicHashDeductionStrategy(DeductionStrategy):
    """
    基于 click_id（或决策键）确定性哈希的扣量策略。

    多 Worker 下同一 click_id 结论一致；比例 = hash%10000 < ratio*10000。
    不再使用进程内 random.random()。
    """

    def should_deduct(
        self,
        config: ConversionDeductionConfig,
        stats: ConversionStats,
        decision_key: str = "",
    ) -> bool:
        ratio = float(config.volume_deduction_ratio or 0)
        if ratio <= 0:
            return False
        if ratio >= 1.0:
            return True
        key = (decision_key or "").strip() or f"seq:{stats.processed}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 10000
        return bucket < int(ratio * 10000)


class RandomDeductionStrategy(DeterministicHashDeductionStrategy):
    """兼容旧配置名 random：内部改为确定性哈希，避免多进程偏差。"""

    pass


class ProportionalDeductionStrategy(DeductionStrategy):
    """按比例扣减策略（每N个扣1个）"""
    
    def should_deduct(
        self,
        config: ConversionDeductionConfig,
        stats: ConversionStats,
        decision_key: str = "",
    ) -> bool:
        """按固定间隔扣量"""
        if config.volume_deduction_ratio <= 0:
            return False
        
        # 防止除零错误
        if config.volume_deduction_ratio >= 1.0:
            return True  # 100%扣量，全部扣减
        
        interval = int(1 / config.volume_deduction_ratio)
        if interval <= 0:
            return False
        
        return (stats.processed + 1) % interval == 0


class RoundRobinDeductionStrategy(DeductionStrategy):
    """轮询扣减策略"""
    
    def should_deduct(
        self,
        config: ConversionDeductionConfig,
        stats: ConversionStats,
        decision_key: str = "",
    ) -> bool:
        """轮询方式扣量"""
        if config.volume_deduction_ratio <= 0:
            return False
        
        # 防止除零错误
        if config.volume_deduction_ratio >= 1.0:
            return True  # 100%扣量，全部扣减
        
        interval = int(1 / config.volume_deduction_ratio)
        if interval <= 0:
            return False
        
        # 与 proportional 一致：用 processed+1，避免首单（processed=0）必扣
        return (stats.processed + 1) % interval == 0


class DeductionStrategyFactory:
    """扣减策略工厂"""
    
    _strategies: Dict[str, DeductionStrategy] = {
        'random': RandomDeductionStrategy(),
        'hash': DeterministicHashDeductionStrategy(),
        'deterministic': DeterministicHashDeductionStrategy(),
        'proportional': ProportionalDeductionStrategy(),
        'round_robin': RoundRobinDeductionStrategy(),
    }
    
    @classmethod
    def get_strategy(cls, strategy_name: str) -> DeductionStrategy:
        """
        获取扣减策略
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            扣减策略实例
        """
        strategy = cls._strategies.get(strategy_name)
        if strategy is None:
            logger.warning(f"未知的扣减策略: {strategy_name}, 使用默认策略 random")
            return cls._strategies['random']
        return strategy


class DeductionManager:
    """扣减管理器"""
    
    def __init__(self, db: AsyncSession):
        """
        初始化扣减管理器
        
        Args:
            db: 数据库会话
        """
        self.db = db
    
    async def find_config(
        self,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None
    ) -> Optional[ConversionDeductionConfig]:
        """
        查找扣减配置（按优先级：Offer > Advertiser > Publisher）
        
        Args:
            advertiser_id: 广告主ID
            offer_id: Offer ID
            publisher_id: 渠道ID
            
        Returns:
            找到的扣减配置，如果没找到返回None
        """
        try:
            from app.core.deduction.deduction_cache import DeductionConfigCache

            cache = DeductionConfigCache(self.db)
            # 优先级1: Offer级别配置
            if offer_id:
                config = await cache.get_config("offer", offer_id)
                if config:
                    logger.debug(f"找到Offer级别扣减配置: offer_id={offer_id}, config_id={config.id}")
                    return config
            
            # 优先级2: 广告主级别配置
            if advertiser_id:
                config = await cache.get_config("advertiser", advertiser_id)
                if config:
                    logger.debug(f"找到广告主级别扣减配置: advertiser_id={advertiser_id}, config_id={config.id}")
                    return config
            
            # 优先级3: 渠道级别配置
            if publisher_id:
                config = await cache.get_config("publisher", publisher_id)
                if config:
                    logger.debug(f"找到渠道级别扣减配置: publisher_id={publisher_id}, config_id={config.id}")
                    return config
            
            return None
            
        except Exception as e:
            logger.error(f"查找扣减配置失败: {str(e)}", exc_info=True)
            if settings.DEDUCTION_FAIL_OPEN:
                return None
            raise
    
    async def _find_offer_config(self, offer_id: int) -> Optional[ConversionDeductionConfig]:
        """查找Offer级别配置"""
        result = await self.db.execute(
            select(ConversionDeductionConfig).where(
                and_(
                    ConversionDeductionConfig.offer_id == offer_id,
                    ConversionDeductionConfig.is_active == True
                )
            ).order_by(ConversionDeductionConfig.priority.desc())
        )
        return result.scalars().first()
    
    async def _find_advertiser_config(self, advertiser_id: int) -> Optional[ConversionDeductionConfig]:
        """查找广告主级别配置"""
        result = await self.db.execute(
            select(ConversionDeductionConfig).where(
                and_(
                    ConversionDeductionConfig.advertiser_id == advertiser_id,
                    ConversionDeductionConfig.is_active == True
                )
            ).order_by(ConversionDeductionConfig.priority.desc())
        )
        return result.scalars().first()
    
    async def _find_publisher_config(self, publisher_id: int) -> Optional[ConversionDeductionConfig]:
        """查找渠道级别配置"""
        result = await self.db.execute(
            select(ConversionDeductionConfig).where(
                and_(
                    ConversionDeductionConfig.publisher_id == publisher_id,
                    ConversionDeductionConfig.is_active == True
                )
            ).order_by(ConversionDeductionConfig.priority.desc())
        )
        return result.scalars().first()
    
    DECISION_SEQ_TTL = 86400 * 2  # 决策序号缓存 2 天

    # Lua：初始化 deducted（NX）+ INCR processed 序号，返回 seq 与 deducted
    _DECISION_STATS_LUA = """
    local seq_key = KEYS[1]
    local deducted_key = KEYS[2]
    local ttl = tonumber(ARGV[1])
    local init_deducted = tonumber(ARGV[2]) or 0
    if redis.call('EXISTS', deducted_key) == 0 then
        redis.call('SET', deducted_key, init_deducted)
        redis.call('EXPIRE', deducted_key, ttl)
    end
    local seq = redis.call('INCR', seq_key)
    if seq == 1 then
        redis.call('EXPIRE', seq_key, ttl)
    end
    local deducted = tonumber(redis.call('GET', deducted_key) or '0')
    return {seq, deducted}
    """

    # Lua：随机策略预留扣量名额；超比例则回退
    _RESERVE_DEDUCTED_LUA = """
    local deducted_key = KEYS[1]
    local limit = tonumber(ARGV[1])
    local ttl = tonumber(ARGV[2])
    local current = tonumber(redis.call('GET', deducted_key) or '0')
    if current >= limit then
        return -1
    end
    local new_val = redis.call('INCR', deducted_key)
    if new_val == 1 then
        redis.call('EXPIRE', deducted_key, ttl)
    end
    if new_val > limit then
        redis.call('DECR', deducted_key)
        return -1
    end
    return new_val
    """

    async def _get_stats_for_decision(
        self,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        hours: int = 24,
    ) -> ConversionStats:
        """
        获取扣量决策用统计：DB 汇总冷启动 + Redis 原子序号/已扣量，避免并发竞态。
        """
        base_stats = await self.get_recent_stats(
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
            hours=hours,
        )
        redis = await get_redis_client()
        if not redis:
            if settings.DEDUCTION_FAIL_OPEN:
                return base_stats
            raise RuntimeError("扣量决策需要 Redis，当前不可用")

        cache_key = self._build_stats_cache_key(
            advertiser_id, offer_id, publisher_id, hours
        )
        seq_key = f"{cache_key}:decision_seq"
        deducted_key = f"{cache_key}:decision_deducted"
        try:
            result = await redis.eval(
                self._DECISION_STATS_LUA,
                2,
                seq_key,
                deducted_key,
                self.DECISION_SEQ_TTL,
                int(base_stats.deducted or 0),
            )
            seq = int(result[0])
            deducted = int(result[1])
            processed = seq - 1
            total = max(seq, base_stats.total)
            return ConversionStats(
                total=total,
                deducted=deducted,
                processed=processed,
            )
        except Exception as e:
            logger.warning("扣量决策 Redis 统计失败: %s", e)
            if settings.DEDUCTION_FAIL_OPEN:
                return base_stats
            raise

    async def _reserve_volume_deduction(
        self,
        *,
        advertiser_id: Optional[int],
        offer_id: Optional[int],
        publisher_id: Optional[int],
        hours: int,
        limit: int,
    ) -> bool:
        """原子预留一条扣量名额；超限返回 False。"""
        if limit <= 0:
            return False
        redis = await get_redis_client()
        if not redis:
            if settings.DEDUCTION_FAIL_OPEN:
                return False
            raise RuntimeError("扣量名额预留需要 Redis，当前不可用")
        cache_key = self._build_stats_cache_key(
            advertiser_id, offer_id, publisher_id, hours
        )
        deducted_key = f"{cache_key}:decision_deducted"
        try:
            new_val = await redis.eval(
                self._RESERVE_DEDUCTED_LUA,
                1,
                deducted_key,
                int(limit),
                self.DECISION_SEQ_TTL,
            )
            return int(new_val) > 0
        except Exception as e:
            logger.warning("扣量名额预留失败: %s", e)
            if settings.DEDUCTION_FAIL_OPEN:
                return False
            raise RuntimeError(f"扣量名额预留失败: {e}") from e

    async def _incr_decision_deducted(
        self,
        *,
        advertiser_id: Optional[int],
        offer_id: Optional[int],
        publisher_id: Optional[int],
        hours: int,
    ) -> None:
        """比例/轮询策略命中后同步递增 Redis deducted（无上限校验）。"""
        redis = await get_redis_client()
        if not redis:
            return
        cache_key = self._build_stats_cache_key(
            advertiser_id, offer_id, publisher_id, hours
        )
        deducted_key = f"{cache_key}:decision_deducted"
        try:
            val = await redis.incr(deducted_key)
            if val == 1:
                await redis.expire(deducted_key, self.DECISION_SEQ_TTL)
        except Exception as e:
            logger.debug("同步 decision_deducted 失败（可忽略）: %s", e)

    async def get_recent_stats(
        self,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        hours: int = 24
    ) -> ConversionStats:
        """
        获取最近的转化统计信息（用于判断是否应该扣减）
        
        Args:
            advertiser_id: 广告主ID
            offer_id: Offer ID
            publisher_id: 渠道ID
            hours: 统计时间范围（小时）
            
        Returns:
            转化统计信息
        """
        try:
            # 尝试从缓存获取
            cache_key = self._build_stats_cache_key(
                advertiser_id, offer_id, publisher_id, hours
            )
            cached_stats = await get_cached(cache_key)
            if cached_stats:
                return ConversionStats(**cached_stats)
            
            # 计算时间范围
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
            
            # 构建查询条件（统计扣减日志表，因为被扣量的转化不保存到主表）
            conditions = [
                ConversionDeductionLog.created_at >= start_time,
                ConversionDeductionLog.created_at <= end_time
            ]
            
            if advertiser_id:
                conditions.append(ConversionDeductionLog.advertiser_id == advertiser_id)
            
            if offer_id:
                conditions.append(ConversionDeductionLog.offer_id == offer_id)
            
            if publisher_id:
                conditions.append(ConversionDeductionLog.publisher_id == publisher_id)
            
            # 一次查出总数与已扣量数，避免同条件两次 COUNT
            stats_row = await self.db.execute(
                select(
                    func.count(ConversionDeductionLog.id),
                    func.coalesce(
                        func.sum(
                            case(
                                (ConversionDeductionLog.deducted_volume > 0, 1),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                ).where(and_(*conditions))
            )
            row = stats_row.one()
            total = int(row[0] or 0)
            deducted = int(row[1] or 0)
            
            # 已处理数量就是total（因为每条转化都会记录日志）
            processed = total
            
            stats = ConversionStats(
                total=total,
                deducted=deducted,
                processed=processed
            )
            
            # 缓存统计结果（SETNX 风格由 cache 层负责；此处仅写）
            await set_cached(cache_key, stats.to_dict(), STATS_CACHE_TTL)
            
            return stats
            
        except Exception as e:
            logger.error(f"获取转化统计失败: {str(e)}", exc_info=True)
            if settings.DEDUCTION_FAIL_OPEN:
                return ConversionStats()
            raise
    
    def _build_stats_cache_key(
        self,
        advertiser_id: Optional[int],
        offer_id: Optional[int],
        publisher_id: Optional[int],
        hours: int
    ) -> str:
        """构建统计缓存键"""
        parts = [STATS_CACHE_PREFIX]
        if advertiser_id:
            parts.append(f"adv:{advertiser_id}")
        if offer_id:
            parts.append(f"offer:{offer_id}")
        if publisher_id:
            parts.append(f"pub:{publisher_id}")
        parts.append(f"hours:{hours}")
        return ":".join(parts)
    
    def should_deduct_volume(
        self,
        config: ConversionDeductionConfig,
        stats: ConversionStats,
        decision_key: str = "",
    ) -> bool:
        """
        判断是否应该扣减转化数量
        
        Args:
            config: 扣减配置
            stats: 转化统计信息
            decision_key: 确定性键（click_id），保证多进程一致
            
        Returns:
            是否应该扣减
        """
        if not config.enable_volume_deduction or config.volume_deduction_ratio <= 0:
            return False
        
        strategy = DeductionStrategyFactory.get_strategy(config.deduction_strategy)
        return strategy.should_deduct(config, stats, decision_key=decision_key)
    
    def calculate_amount_deduction(
        self,
        original_amount: Decimal | float | int | str | None,
        config: ConversionDeductionConfig
    ) -> Tuple[Decimal, Decimal]:
        """
        计算扣减后的金额

        Args:
            original_amount: 原始金额
            config: 扣减配置

        Returns:
            (扣减后金额, 扣减金额)
        """
        if not config.enable_amount_deduction or config.amount_deduction_ratio <= 0:
            return Decimal(str(original_amount or 0)), Decimal("0")

        orig = Decimal(str(original_amount or 0))
        ratio = Decimal(str(config.amount_deduction_ratio))
        deduction_amount = orig * ratio
        final_amount = orig - deduction_amount

        return final_amount, deduction_amount
    
    async def apply_deduction(
        self,
        conversion_data: Dict[str, Any],
        config: ConversionDeductionConfig,
        click_id: Optional[str] = None,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None
    ) -> DeductionResult:
        """
        应用扣减（可能同时扣量和扣金额）
        
        Args:
            conversion_data: 转化数据字典
            config: 扣减配置
            click_id: 点击ID
            advertiser_id: 广告主ID
            offer_id: Offer ID
            publisher_id: 渠道ID
            
        Returns:
            扣减结果
        """
        result = DeductionResult(
            original_volume=1,
            original_amount=Decimal(str(conversion_data.get('original_payout', 0) or 0)),
            final_volume=1,
            final_amount=Decimal(str(conversion_data.get('original_payout', 0) or 0)),
        )
        
        # 获取转化统计（Redis 原子序号 + deducted，避免 60s 缓存竞态）
        stats = await self._get_stats_for_decision(
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
            hours=24
        )
        
        # 判断是否扣量（确定性哈希 / 间隔策略 + Redis 原子预留防超扣）
        if config.enable_volume_deduction:
            strategy_name = (config.deduction_strategy or "random").lower()
            decision_key = (click_id or "").strip() or f"offer:{offer_id}:seq:{stats.processed}"
            want_deduct = self.should_deduct_volume(config, stats, decision_key=decision_key)
            if want_deduct:
                if strategy_name in ("random", "hash", "deterministic"):
                    # 哈希命中后仍按目标比例原子预留，避免并发过量扣
                    ratio = float(config.volume_deduction_ratio or 0)
                    limit = int(stats.total * ratio) if stats.total > 0 else 10**9
                    if stats.total <= 0:
                        # 无总量窗口时仅按哈希结论 + 递增 deducted
                        result.should_deduct_volume = True
                        await self._incr_decision_deducted(
                            advertiser_id=advertiser_id,
                            offer_id=offer_id,
                            publisher_id=publisher_id,
                            hours=24,
                        )
                    else:
                        reserved = await self._reserve_volume_deduction(
                            advertiser_id=advertiser_id,
                            offer_id=offer_id,
                            publisher_id=publisher_id,
                            hours=24,
                            limit=limit,
                        )
                        result.should_deduct_volume = reserved
                else:
                    result.should_deduct_volume = True
                    await self._incr_decision_deducted(
                        advertiser_id=advertiser_id,
                        offer_id=offer_id,
                        publisher_id=publisher_id,
                        hours=24,
                    )
            if result.should_deduct_volume:
                result.final_volume = 0
                result.deducted_volume = 1
                result.deduction_type = 'volume'
        
        # 计算扣金额
        if config.enable_amount_deduction:
            result.should_deduct_amount = True
            result.final_amount, result.deducted_amount = self.calculate_amount_deduction(
                result.original_amount, config
            )
            if result.deduction_type:
                result.deduction_type = 'both'
            else:
                result.deduction_type = 'amount'
        
        return result
    
    async def log_deduction(
        self,
        deduction_result: DeductionResult,
        conversion_id: Optional[int] = None,
        click_id: Optional[str] = None,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        config: Optional[ConversionDeductionConfig] = None,
        deduction_reason: Optional[str] = None
    ) -> ConversionDeductionLog:
        """
        记录扣减日志
        
        Args:
            deduction_result: 扣减结果
            conversion_id: 转化记录ID
            click_id: 点击ID
            advertiser_id: 广告主ID
            offer_id: Offer ID
            publisher_id: 渠道ID
            config: 扣减配置
            deduction_reason: 扣减原因
            
        Returns:
            扣减日志记录
        """
        log = ConversionDeductionLog(
            conversion_id=conversion_id,
            click_id=click_id,
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
            original_volume=deduction_result.original_volume,
            original_amount=deduction_result.original_amount,
            deducted_volume=deduction_result.deducted_volume,
            deducted_amount=deduction_result.deducted_amount,
            final_volume=deduction_result.final_volume,
            final_amount=deduction_result.final_amount,
            deduction_config_id=config.id if config else None,
            volume_deduction_ratio=config.volume_deduction_ratio if config and config.enable_volume_deduction else None,
            amount_deduction_ratio=config.amount_deduction_ratio if config and config.enable_amount_deduction else None,
            deduction_strategy=config.deduction_strategy if config else None,
            deduction_reason=deduction_reason
        )
        
        self.db.add(log)
        await self.db.flush()  # 不提交，让调用者决定何时提交
        
        # 清除相关统计缓存
        await self._invalidate_stats_cache(advertiser_id, offer_id, publisher_id)
        
        return log
    
    async def _invalidate_stats_cache(
        self,
        advertiser_id: Optional[int],
        offer_id: Optional[int],
        publisher_id: Optional[int]
    ) -> None:
        """
        清除统计缓存
        
        注意：由于统计缓存键的格式是：
        cpl:conversion_stats:adv:{id}:offer:{id}:pub:{id}:hours:{hours}
        
        我们需要清除所有包含指定ID的缓存键，因为统计会变化。
        例如：如果有advertiser_id=1，需要清除所有包含adv:1的缓存。
        """
        patterns = []
        if advertiser_id:
            # 匹配所有包含该广告主ID的缓存键
            patterns.append(f"*adv:{advertiser_id}*")
        if offer_id:
            # 匹配所有包含该Offer ID的缓存键
            patterns.append(f"*offer:{offer_id}*")
        if publisher_id:
            # 匹配所有包含该渠道ID的缓存键
            patterns.append(f"*pub:{publisher_id}*")
        
        # 如果没有指定任何ID，清除所有统计缓存
        if not patterns:
            patterns.append("*")
        
        # 清除匹配的缓存
        # 注意：set_cached和get_cached会在key前添加CACHE_PREFIX（query_cache:）
        # 所以实际的缓存键是：query_cache:cpl:conversion_stats:adv:1:hours:24
        # invalidate_cache函数也会添加CACHE_PREFIX并在末尾添加*，所以我们需要直接使用Redis删除
        try:
            redis = await get_redis_client()
            if not redis:
                return
            
            # 构建完整的缓存键模式（包含query_cache:前缀）
            # 实际的缓存键格式：query_cache:cpl:conversion_stats:adv:1:hours:24
            base_pattern = f"{CACHE_PREFIX}{STATS_CACHE_PREFIX}"
            patterns_to_match = []
            
            for pattern in patterns:
                # pattern格式：*adv:1* 或 *offer:2* 或 *pub:3*
                # 构建完整匹配模式：query_cache:cpl:conversion_stats:*adv:1*
                full_pattern = f"{base_pattern}{pattern}"
                patterns_to_match.append(full_pattern)
            
            # 使用SCAN而不是KEYS（更安全，不会阻塞）
            keys_to_delete = []
            for pattern in patterns_to_match:
                async for key in redis.scan_iter(match=pattern):
                    keys_to_delete.append(key)
                    # 批量删除，每100个删除一次
                    if len(keys_to_delete) >= 100:
                        await redis.delete(*keys_to_delete)
                        keys_to_delete = []
            
            # 删除剩余的
            if keys_to_delete:
                deleted_count = await redis.delete(*keys_to_delete)
                logger.debug(f"清除了 {deleted_count} 个统计缓存键")
        except Exception as e:
            logger.warning(f"清除统计缓存失败: {e}")


# 向后兼容的函数接口
async def find_deduction_config(
    db: AsyncSession,
    advertiser_id: Optional[int] = None,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None
) -> Optional[ConversionDeductionConfig]:
    """查找扣减配置（向后兼容）"""
    manager = DeductionManager(db)
    return await manager.find_config(advertiser_id, offer_id, publisher_id)


async def get_recent_conversion_stats(
    db: AsyncSession,
    advertiser_id: Optional[int] = None,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None,
    hours: int = 24
) -> Dict[str, Any]:
    """获取最近的转化统计信息（向后兼容）"""
    manager = DeductionManager(db)
    stats = await manager.get_recent_stats(advertiser_id, offer_id, publisher_id, hours)
    return stats.to_dict()


def should_deduct_volume(
    config: ConversionDeductionConfig,
    stats: Dict[str, Any]
) -> bool:
    """判断是否应该扣减转化数量（向后兼容）"""
    stats_obj = ConversionStats(**stats)
    manager = DeductionManager(None)  # 临时管理器，只用于调用方法
    return manager.should_deduct_volume(config, stats_obj)


def calculate_amount_deduction(
    original_amount: Decimal | float | int | str | None,
    config: ConversionDeductionConfig
) -> Tuple[Decimal, Decimal]:
    """计算扣减后的金额（向后兼容）"""
    manager = DeductionManager(None)  # 临时管理器，只用于调用方法
    return manager.calculate_amount_deduction(original_amount, config)


async def apply_deduction(
    db: AsyncSession,
    conversion_data: Dict[str, Any],
    config: ConversionDeductionConfig,
    click_id: Optional[str] = None,
    advertiser_id: Optional[int] = None,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None
) -> Dict[str, Any]:
    """应用扣减（向后兼容）"""
    manager = DeductionManager(db)
    result = await manager.apply_deduction(
        conversion_data, config, click_id, advertiser_id, offer_id, publisher_id
    )
    return result.to_dict()


async def log_deduction(
    db: AsyncSession,
    deduction_result: Dict[str, Any],
    conversion_id: Optional[int] = None,
    click_id: Optional[str] = None,
    advertiser_id: Optional[int] = None,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None,
    config: Optional[ConversionDeductionConfig] = None,
    deduction_reason: Optional[str] = None
) -> ConversionDeductionLog:
    """记录扣减日志（向后兼容）"""
    manager = DeductionManager(db)
    result_obj = DeductionResult(**deduction_result)
    return await manager.log_deduction(
        result_obj, conversion_id, click_id, advertiser_id, offer_id, publisher_id, config, deduction_reason
    )
