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
import random
from typing import Optional, Tuple, Dict, Any, Protocol
from abc import ABC, abstractmethod
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func
from datetime import datetime, timedelta

from app.models.models import (
    ConversionDeductionConfig, 
    ConversionDeductionLog,
)
from app.core.cache import get_cached, set_cached, invalidate_cache

logger = logging.getLogger(__name__)

# 缓存配置
CONFIG_CACHE_TTL = 300  # 配置缓存5分钟
CONFIG_CACHE_PREFIX = "cpl:deduction_config:"
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
    original_amount: float = 0.0
    final_volume: int = 1
    final_amount: float = 0.0
    deducted_volume: int = 0
    deducted_amount: float = 0.0
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
        stats: ConversionStats
    ) -> bool:
        """
        判断是否应该扣减当前转化
        
        Args:
            config: 扣减配置
            stats: 转化统计信息
            
        Returns:
            是否应该扣减
        """
        pass


class RandomDeductionStrategy(DeductionStrategy):
    """随机扣减策略"""
    
    def should_deduct(
        self,
        config: ConversionDeductionConfig,
        stats: ConversionStats
    ) -> bool:
        """随机扣减，但确保总体比例正确"""
        if stats.total == 0:
            return False
        
        should_deduct_count = int(stats.total * config.volume_deduction_ratio)
        
        if stats.deducted >= should_deduct_count:
            return False
        
        remaining_to_deduct = should_deduct_count - stats.deducted
        remaining_conversions = stats.total - stats.processed
        
        if remaining_conversions == 0:
            return False
        
        probability = remaining_to_deduct / remaining_conversions
        return random.random() < probability


class ProportionalDeductionStrategy(DeductionStrategy):
    """按比例扣减策略（每N个扣1个）"""
    
    def should_deduct(
        self,
        config: ConversionDeductionConfig,
        stats: ConversionStats
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
        stats: ConversionStats
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
        
        return stats.processed % interval == 0


class DeductionStrategyFactory:
    """扣减策略工厂"""
    
    _strategies: Dict[str, DeductionStrategy] = {
        'random': RandomDeductionStrategy(),
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
            # 优先级1: Offer级别配置
            if offer_id:
                config = await self._get_cached_config('offer', offer_id)
                if config:
                    logger.debug(f"找到Offer级别扣减配置: offer_id={offer_id}, config_id={config.id}")
                    return config
                
                config = await self._find_offer_config(offer_id)
                if config:
                    await self._cache_config('offer', offer_id, config)
                    return config
            
            # 优先级2: 广告主级别配置
            if advertiser_id:
                config = await self._get_cached_config('advertiser', advertiser_id)
                if config:
                    logger.debug(f"找到广告主级别扣减配置: advertiser_id={advertiser_id}, config_id={config.id}")
                    return config
                
                config = await self._find_advertiser_config(advertiser_id)
                if config:
                    await self._cache_config('advertiser', advertiser_id, config)
                    return config
            
            # 优先级3: 渠道级别配置
            if publisher_id:
                config = await self._get_cached_config('publisher', publisher_id)
                if config:
                    logger.debug(f"找到渠道级别扣减配置: publisher_id={publisher_id}, config_id={config.id}")
                    return config
                
                config = await self._find_publisher_config(publisher_id)
                if config:
                    await self._cache_config('publisher', publisher_id, config)
                    return config
            
            return None
            
        except Exception as e:
            logger.error(f"查找扣减配置失败: {str(e)}", exc_info=True)
            return None
    
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
    
    async def _get_cached_config(
        self,
        level: str,
        target_id: int
    ) -> Optional[ConversionDeductionConfig]:
        """
        从缓存获取配置ID，然后从数据库加载完整配置
        
        优化方案：只缓存配置ID，避免序列化问题
        """
        cache_key = f"{CONFIG_CACHE_PREFIX}{level}:{target_id}"
        cached_config_id = await get_cached(cache_key)
        if cached_config_id:
            try:
                # 从数据库加载完整配置对象
                result = await self.db.execute(
                    select(ConversionDeductionConfig).where(
                        ConversionDeductionConfig.id == cached_config_id,
                        ConversionDeductionConfig.is_active == True
                    )
                )
                config = result.scalars().first()
                if config:
                    logger.debug(f"从缓存配置ID加载配置成功: config_id={config.id}")
                    return config
                else:
                    # 配置已不存在或已禁用，清除缓存
                    await invalidate_cache(cache_key)
            except Exception as e:
                logger.debug(f"从缓存配置ID加载配置失败: {e}")
                # 清除无效缓存
                await invalidate_cache(cache_key)
        return None
    
    async def _cache_config(
        self,
        level: str,
        target_id: int,
        config: ConversionDeductionConfig
    ) -> None:
        """
        缓存配置ID（而不是整个配置对象）
        
        优化方案：只缓存配置ID，避免序列化问题，查询时再从数据库加载
        """
        if not config or not config.id:
            return
        
        cache_key = f"{CONFIG_CACHE_PREFIX}{level}:{target_id}"
        try:
            # 只缓存配置ID（整数，易于序列化）
            await set_cached(cache_key, config.id, CONFIG_CACHE_TTL)
            logger.debug(f"缓存配置ID成功: cache_key={cache_key}, config_id={config.id}")
        except Exception as e:
            logger.warning(f"缓存配置ID失败: {e}")
    
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
            
            # 统计总数（所有转化，包括被扣量的和未扣量的）
            total_result = await self.db.execute(
                select(func.count(ConversionDeductionLog.id)).where(and_(*conditions))
            )
            total = total_result.scalar() or 0
            
            # 统计已扣减数量（被扣量的转化，deducted_volume > 0）
            deducted_result = await self.db.execute(
                select(func.count(ConversionDeductionLog.id)).where(
                    and_(*conditions, ConversionDeductionLog.deducted_volume > 0)
                )
            )
            deducted = deducted_result.scalar() or 0
            
            # 已处理数量就是total（因为每条转化都会记录日志）
            processed = total
            
            stats = ConversionStats(
                total=total,
                deducted=deducted,
                processed=processed
            )
            
            # 缓存统计结果
            await set_cached(cache_key, stats.to_dict(), STATS_CACHE_TTL)
            
            return stats
            
        except Exception as e:
            logger.error(f"获取转化统计失败: {str(e)}", exc_info=True)
            return ConversionStats()
    
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
        stats: ConversionStats
    ) -> bool:
        """
        判断是否应该扣减转化数量
        
        Args:
            config: 扣减配置
            stats: 转化统计信息
            
        Returns:
            是否应该扣减
        """
        if not config.enable_volume_deduction or config.volume_deduction_ratio <= 0:
            return False
        
        strategy = DeductionStrategyFactory.get_strategy(config.deduction_strategy)
        return strategy.should_deduct(config, stats)
    
    def calculate_amount_deduction(
        self,
        original_amount: float,
        config: ConversionDeductionConfig
    ) -> Tuple[float, float]:
        """
        计算扣减后的金额
        
        Args:
            original_amount: 原始金额
            config: 扣减配置
            
        Returns:
            (扣减后金额, 扣减金额)
        """
        if not config.enable_amount_deduction or config.amount_deduction_ratio <= 0:
            return original_amount, 0.0
        
        deduction_amount = original_amount * config.amount_deduction_ratio
        final_amount = original_amount - deduction_amount
        
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
            original_amount=conversion_data.get('original_payout', 0.0) or 0.0,
            final_volume=1,
            final_amount=conversion_data.get('original_payout', 0.0) or 0.0,
        )
        
        # 获取转化统计
        stats = await self.get_recent_stats(
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
            hours=24
        )
        
        # 判断是否扣量
        if config.enable_volume_deduction:
            result.should_deduct_volume = self.should_deduct_volume(config, stats)
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
            from app.core.redis_client import get_redis_client
            from app.core.cache import CACHE_PREFIX
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
    original_amount: float,
    config: ConversionDeductionConfig
) -> Tuple[float, float]:
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
