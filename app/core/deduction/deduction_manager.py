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
from typing import Optional, Tuple, Dict, Any
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from datetime import timedelta

from app.models.models import (
    ConversionDeductionConfig, 
    ConversionDeductionLog,
    PostbackConversion,
)
from app.core.infrastructure.cache_compat import (
    CACHE_PREFIX,
    invalidate_cache,
    legacy_get_cached as get_cached,
    legacy_set_cached as set_cached,
)
from app.core.redis_client import get_redis_client
from app.core.config import settings
from app.core.utils import get_app_now_naive, get_app_now_naive_floor_second
from app.core.third_party_currency import resolve_currency

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
    currency: str = "USD"
    currency_source: str = "system_fallback_usd"
    
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
            'deduction_type': self.deduction_type,
            'currency': self.currency,
            'currency_source': self.currency_source,
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
        # 必须在 Generation、Redis 缓存和配置读取之前锁定全部候选 scope。
        # 所有 scope 按固定字典序获取，避免批量写入口与 Postback 形成反向锁顺序。
        from app.services.cpl.deduction.helpers import lock_deduction_scopes

        candidate_scopes = []
        if advertiser_id:
            candidate_scopes.append(("advertiser", advertiser_id))
        if offer_id:
            candidate_scopes.append(("offer", offer_id))
        if publisher_id:
            candidate_scopes.append(("publisher", publisher_id))
        await lock_deduction_scopes(self.db, candidate_scopes)

        try:
            # 财务决策不读取 Redis 配置缓存或 Generation。
            # scope 锁已在上方获取；以下 SELECT FOR UPDATE 为 MySQL current read，
            # 避免 REPEATABLE READ 事务复用锁前快照。
            if offer_id:
                config = await self._find_offer_config(offer_id)
                if config:
                    return config
            if advertiser_id:
                config = await self._find_advertiser_config(advertiser_id)
                if config:
                    return config
            if publisher_id:
                config = await self._find_publisher_config(publisher_id)
                if config:
                    return config
            return None
        except Exception as e:
            logger.error("查找扣量配置失败: %s", str(e), exc_info=True)
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
            ).order_by(
                ConversionDeductionConfig.priority.desc(),
                ConversionDeductionConfig.id.asc(),
            ).with_for_update()
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
            ).order_by(
                ConversionDeductionConfig.priority.desc(),
                ConversionDeductionConfig.id.asc(),
            ).with_for_update()
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
            ).order_by(
                ConversionDeductionConfig.priority.desc(),
                ConversionDeductionConfig.id.asc(),
            ).with_for_update()
        )
        return result.scalars().first()
    
    async def _get_stats_for_decision(
        self,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        hours: int = 24,
    ) -> ConversionStats:
        """
        从 MySQL 读取扣量决策基线。

        调用前必须由 find_config() 在当前 Session 中取得全部候选 scope 锁；
        这些锁一直持有到 Postback 外层事务提交/回滚。正常转化由
        postback_conversions 计数，未入库的扣量事件由同事务提交的
        conversion_deduction_logs 计数，因此 MySQL 回滚会自动撤销统计贡献。
        Redis 不再参与财务决策，避免 Redis INCR 与 MySQL COMMIT 跨事务漂移。
        """
        return await self.get_recent_stats(
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
            hours=hours,
            strict=True,
        )

    async def get_recent_stats(
        self,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        hours: int = 24,
        strict: bool = False,
    ) -> ConversionStats:
        """
        获取最近的转化统计信息（用于判断是否应该扣减）
        
        Args:
            advertiser_id: 广告主ID
            offer_id: Offer ID
            publisher_id: 渠道ID
            hours: 最近 N 小时内系统接收/入库的转化范围（使用 created_at，不代表上游事件发生时间）
            
        Returns:
            转化统计信息
        """
        try:
            # strict 决策路径必须直接读取数据库权威统计；60 秒缓存仅供展示/非严格查询。
            # 否则窗口内旧事件滚出后，缓存仍会污染扣量判断。
            cache_key = self._build_stats_cache_key(
                advertiser_id, offer_id, publisher_id, hours
            )
            if not strict:
                cached_stats = await get_cached(cache_key)
                if cached_stats:
                    return ConversionStats(**cached_stats)
            
            # 统计窗口内的已入库转化 + 未入库的扣量命中。
            # 正常转化不一定有 ConversionDeductionLog；扣金额日志对应的转化已在
            # postback_conversions 中，不能再重复计数。仅将 conversion_id 为空且
            # deducted_volume > 0 的日志作为“未入库扣量转化”补入统计。
            end_time = get_app_now_naive()
            start_time = end_time - timedelta(hours=hours)

            # 使用半开区间 [start_time, end_time)，避免相邻窗口边界事件重复计数。
            conversion_conditions = [
                PostbackConversion.created_at >= start_time,
                PostbackConversion.created_at < end_time,
            ]
            volume_log_conditions = [
                ConversionDeductionLog.created_at >= start_time,
                ConversionDeductionLog.created_at < end_time,
                ConversionDeductionLog.deducted_volume > 0,
                ConversionDeductionLog.conversion_id.is_(None),
            ]

            if advertiser_id:
                conversion_conditions.append(PostbackConversion.advertiser_id == advertiser_id)
                volume_log_conditions.append(ConversionDeductionLog.advertiser_id == advertiser_id)

            if offer_id:
                conversion_conditions.append(PostbackConversion.offer_id == offer_id)
                volume_log_conditions.append(ConversionDeductionLog.offer_id == offer_id)

            if publisher_id:
                conversion_conditions.append(PostbackConversion.publisher_id == publisher_id)
                volume_log_conditions.append(ConversionDeductionLog.publisher_id == publisher_id)

            conversion_count_result = await self.db.execute(
                select(func.count(PostbackConversion.id)).where(
                    and_(*conversion_conditions)
                )
            )
            conversion_count = int(conversion_count_result.scalar_one() or 0)

            volume_log_count_result = await self.db.execute(
                select(func.count(ConversionDeductionLog.id)).where(
                    and_(*volume_log_conditions)
                )
            )
            volume_log_count = int(volume_log_count_result.scalar_one() or 0)

            deducted_conversion_conditions = [
                *conversion_conditions,
                PostbackConversion.deducted_volume > 0,
            ]
            deducted_conversion_result = await self.db.execute(
                select(func.count(PostbackConversion.id)).where(
                    and_(*deducted_conversion_conditions)
                )
            )
            deducted_conversion_count = int(deducted_conversion_result.scalar_one() or 0)

            total = conversion_count + volume_log_count
            deducted = deducted_conversion_count + volume_log_count
            processed = total
            
            stats = ConversionStats(
                total=total,
                deducted=deducted,
                processed=processed
            )
            
            # strict 决策统计不写入展示缓存，避免被后续非严格查询误认为权威数据。
            if not strict:
                await set_cached(cache_key, stats.to_dict(), STATS_CACHE_TTL)
            
            return stats
            
        except Exception as e:
            logger.error(f"获取转化统计失败: {str(e)}", exc_info=True)
            if settings.DEDUCTION_FAIL_OPEN and not strict:
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
        # 新键空间隔离旧统计口径缓存，避免继续使用仅含扣减日志的旧结果。
        parts.append("schema:v2")
        return ":".join(parts)
    
    @staticmethod
    def _build_event_decision_key(event_identity: Optional[Dict[str, str]]) -> Optional[str]:
        """构建稳定的事件级决策键；禁止使用 click_id 或递增序号替代事件身份。"""
        if not isinstance(event_identity, dict):
            return None
        platform = str(event_identity.get("platform") or "").strip()
        conversion_id = str(event_identity.get("conversion_id") or "").strip()
        event_name = str(event_identity.get("event_name") or "").strip()
        # 与数据库字段宽度一致，提前拒绝可能被截断或产生碰撞的身份字段。
        if (
            not platform or len(platform) > 50
            or not conversion_id or len(conversion_id) > 255
            or not event_name or len(event_name) > 100
        ):
            return None
        encoded_parts = [value.encode("utf-8") for value in (platform, conversion_id, event_name)]
        # 长度前缀编码，避免简单拼接分隔符导致身份歧义。
        payload = b"".join(len(part).to_bytes(4, "big") + part for part in encoded_parts)
        return "event:v1:" + hashlib.sha256(payload).hexdigest()

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
            decision_key: 由 platform + conversion_id + event_name 构建的稳定事件键
            
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
        # 保持输入金额的小数位数；按十进制四舍五入，不经过 float。
        amount_quantum = Decimal(1).scaleb(orig.as_tuple().exponent)
        deduction_amount = (orig * ratio).quantize(
            amount_quantum, rounding=ROUND_HALF_UP
        )
        final_amount = orig - deduction_amount

        return final_amount, deduction_amount
    
    @staticmethod
    def _stats_scope_for_config(
        config: ConversionDeductionConfig,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
    ) -> Dict[str, Optional[int]]:
        """统计范围必须严格跟随最终命中的配置层级，而不是请求携带的所有维度。"""
        scope_fields = ("advertiser_id", "offer_id", "publisher_id")
        # 兼容仅用于单元测试的轻量替身；真实 ORM 配置模型始终具有这三个字段。
        if not any(hasattr(config, field) for field in scope_fields):
            return {
                "advertiser_id": advertiser_id,
                "offer_id": offer_id,
                "publisher_id": publisher_id,
            }

        selected = [
            (field, getattr(config, field, None))
            for field in scope_fields
            if getattr(config, field, None) is not None
        ]
        if len(selected) != 1:
            raise ValueError("扣量配置必须且只能有一个有效统计 scope")
        field, target_id = selected[0]
        if (
            not isinstance(target_id, int)
            or isinstance(target_id, bool)
            or target_id <= 0
        ):
            raise ValueError("扣量配置统计 scope ID 必须为正整数")
        return {
            "advertiser_id": target_id if field == "advertiser_id" else None,
            "offer_id": target_id if field == "offer_id" else None,
            "publisher_id": target_id if field == "publisher_id" else None,
        }

    async def apply_deduction(
        self,
        conversion_data: Dict[str, Any],
        config: ConversionDeductionConfig,
        click_id: Optional[str] = None,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        event_identity: Optional[Dict[str, str]] = None,
    ) -> DeductionResult:
        """
        应用扣减（可能同时扣量和扣金额）
        
        Args:
            conversion_data: 转化数据字典
            config: 扣减配置
            click_id: 点击归因 ID（不参与事件决策键）
            advertiser_id: 广告主ID
            offer_id: Offer ID
            publisher_id: 渠道ID
            
        Returns:
            扣减结果
        """
        currency, currency_source = resolve_currency(
            conversion_data.get("currency"),
            source=conversion_data.get("currency_source"),
        )
        result = DeductionResult(
            original_volume=1,
            original_amount=Decimal(str(conversion_data.get('original_payout', 0) or 0)),
            final_volume=1,
            final_amount=Decimal(str(conversion_data.get('original_payout', 0) or 0)),
            currency=currency,
            currency_source=currency_source,
        )
        
        # 只有具备稳定事件身份时才允许扣量；click_id 不是转化事件唯一键。
        volume_decision_available = bool(
            config.enable_volume_deduction
            and Decimal(str(config.volume_deduction_ratio or 0)) > 0
        )
        event_decision_key = self._build_event_decision_key(event_identity)
        if volume_decision_available and not event_decision_key:
            logger.warning(
                "扣量事件身份未验证，本次跳过扣量：scope_offer_id=%s",
                offer_id,
            )
            volume_decision_available = False

        stats = ConversionStats()
        if volume_decision_available:
            try:
                # 必须在 find_config() 已锁定全部候选 scope 的同一事务内执行。
                # DB 统计只包含此前已提交事件；当前事件在本事务结束时写入
                # postback_conversions 或 volume deduction log。
                stats_scope = self._stats_scope_for_config(
                    config,
                    advertiser_id=advertiser_id,
                    offer_id=offer_id,
                    publisher_id=publisher_id,
                )
                stats = await self._get_stats_for_decision(
                    **stats_scope,
                    hours=24,
                )
            except Exception as exc:
                if not settings.DEDUCTION_FAIL_OPEN:
                    raise
                # fail-open 仅放行本次扣量，不得用不完整统计继续执行财务扣量。
                logger.warning(
                    "MySQL 扣量统计不可用，本次跳过扣量但继续计算扣金额: %s",
                    exc,
                )
                volume_decision_available = False

        if volume_decision_available:
            decision_key = event_decision_key or ""
            want_deduct = self.should_deduct_volume(
                config,
                stats,
                decision_key=decision_key,
            )
            if want_deduct:
                ratio = Decimal(str(config.volume_deduction_ratio or 0))
                # stats.total 不含当前未提交事件，因此额度上限按 total + 1 计算。
                # scope 行锁保证同一配置范围内的决策串行；日志/转化与事件收据
                # 同事务提交，回滚会自然释放名额，24h 窗口也由 SQL 自动滚动。
                allowed_deductions = max(
                    1,
                    int(
                        (Decimal(stats.total + 1) * ratio).to_integral_value(
                            rounding="ROUND_FLOOR"
                        )
                    ),
                )
                result.should_deduct_volume = (
                    stats.deducted < allowed_deductions
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
            currency=deduction_result.currency,
            currency_source=deduction_result.currency_source,
            deduction_config_id=config.id if config else None,
            volume_deduction_ratio=config.volume_deduction_ratio if config and config.enable_volume_deduction else None,
            amount_deduction_ratio=config.amount_deduction_ratio if config and config.enable_amount_deduction else None,
            deduction_strategy=config.deduction_strategy if config else None,
            deduction_reason=deduction_reason,
            created_at=get_app_now_naive_floor_second(),
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
    publisher_id: Optional[int] = None,
    event_identity: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """应用扣减（向后兼容）"""
    manager = DeductionManager(db)
    result = await manager.apply_deduction(
        conversion_data,
        config,
        click_id,
        advertiser_id,
        offer_id,
        publisher_id,
        event_identity=event_identity,
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
