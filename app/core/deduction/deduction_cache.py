"""
扣量配置缓存管理

提供扣量配置的缓存、读取、失效功能
解决 SQLAlchemy 对象序列化问题
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_

from app.models.models import ConversionDeductionConfig
from app.core.infrastructure.cache_compat import get_cached, set_cached

logger = logging.getLogger(__name__)

# 缓存配置
CONFIG_CACHE_TTL = 300  # 5 分钟
CONFIG_CACHE_PREFIX = "cpl:deduction_config:"


class DeductionConfigCache:
    """扣量配置缓存管理器"""
    
    def __init__(self, db: AsyncSession):
        """
        Args:
            db: 异步数据库会话，缓存未命中时从此加载 ConversionDeductionConfig
        """
        self.db = db
    
    async def get_config(
        self,
        level: str,
        target_id: int
    ) -> Optional[ConversionDeductionConfig]:
        """
        获取配置（带缓存）
        
        Args:
            level: 配置级别（offer/publisher/advertiser）
            target_id: 目标 ID
        
        Returns:
            配置对象或 None
        """
        # 尝试从缓存获取
        cache_key = f"{CONFIG_CACHE_PREFIX}{level}:{target_id}"
        cached_data = await get_cached(cache_key, key_prefix='deduction')
        
        if cached_data and isinstance(cached_data, dict):
            try:
                # 从缓存字典重建配置对象（字段与 ORM 对齐）
                config = ConversionDeductionConfig(
                    id=cached_data.get('id'),
                    offer_id=cached_data.get('offer_id'),
                    publisher_id=cached_data.get('publisher_id'),
                    advertiser_id=cached_data.get('advertiser_id'),
                    volume_deduction_ratio=float(cached_data.get('volume_deduction_ratio', 0) or 0),
                    amount_deduction_ratio=float(cached_data.get('amount_deduction_ratio', 0) or 0),
                    priority=int(cached_data.get('priority', 0) or 0),
                    is_active=bool(cached_data.get('is_active', True)),
                    deduction_strategy=cached_data.get('deduction_strategy')
                    or cached_data.get('strategy')
                    or 'random',
                    enable_volume_deduction=bool(cached_data.get('enable_volume_deduction', False)),
                    enable_amount_deduction=bool(cached_data.get('enable_amount_deduction', False)),
                    created_at=cached_data.get('created_at'),
                    updated_at=cached_data.get('updated_at'),
                )
                logger.debug(f"缓存命中：deduction_config:{level}:{target_id}")
                return config
            except Exception as e:
                logger.warning(f"从缓存重建配置失败：{e}")
                return None
        
        # 缓存未命中，从数据库加载
        config = await self._load_from_db(level, target_id)
        
        if config:
            # 写入缓存
            await self._save_to_cache(level, target_id, config)
        
        return config
    
    async def _load_from_db(self, level: str, target_id: int) -> Optional[ConversionDeductionConfig]:
        """从数据库加载配置"""
        try:
            if level == 'offer':
                result = await self.db.execute(
                    select(ConversionDeductionConfig).where(
                        and_(
                            ConversionDeductionConfig.offer_id == target_id,
                            ConversionDeductionConfig.is_active == True
                        )
                    ).order_by(ConversionDeductionConfig.priority.desc()).limit(1)
                )
            elif level == 'publisher':
                result = await self.db.execute(
                    select(ConversionDeductionConfig).where(
                        and_(
                            ConversionDeductionConfig.publisher_id == target_id,
                            ConversionDeductionConfig.is_active == True
                        )
                    ).order_by(ConversionDeductionConfig.priority.desc()).limit(1)
                )
            elif level == 'advertiser':
                result = await self.db.execute(
                    select(ConversionDeductionConfig).where(
                        and_(
                            ConversionDeductionConfig.advertiser_id == target_id,
                            ConversionDeductionConfig.is_active == True
                        )
                    ).order_by(ConversionDeductionConfig.priority.desc()).limit(1)
                )
            else:
                logger.warning(f"未知配置级别：{level}")
                return None
            
            return result.scalars().first()
        
        except Exception as e:
            logger.error(f"从数据库加载配置失败：{e}", exc_info=True)
            return None
    
    async def _save_to_cache(self, level: str, target_id: int, config: ConversionDeductionConfig):
        """保存配置到缓存"""
        cache_key = f"{CONFIG_CACHE_PREFIX}{level}:{target_id}"
        
        # 序列化为字典（避免 SQLAlchemy 对象序列化问题）
        config_dict = {
            'id': config.id,
            'offer_id': config.offer_id,
            'publisher_id': config.publisher_id,
            'advertiser_id': config.advertiser_id,
            'volume_deduction_ratio': float(config.volume_deduction_ratio or 0),
            'amount_deduction_ratio': float(config.amount_deduction_ratio or 0),
            'priority': config.priority,
            'is_active': config.is_active,
            'deduction_strategy': config.deduction_strategy or 'random',
            'enable_volume_deduction': bool(config.enable_volume_deduction),
            'enable_amount_deduction': bool(config.enable_amount_deduction),
            'created_at': str(config.created_at) if config.created_at else None,
            'updated_at': str(config.updated_at) if config.updated_at else None,
        }
        
        await set_cached(cache_key, config_dict, ttl=CONFIG_CACHE_TTL, key_prefix='deduction')
        logger.debug(f"配置已缓存：deduction_config:{level}:{target_id}, TTL={CONFIG_CACHE_TTL}s")
    
    async def invalidate(self, level: str = None, target_id: int = None):
        """
        失效缓存
        
        Args:
            level: 配置级别（可选，不传则失效所有）
            target_id: 目标 ID（可选）
        """
        from app.core.infrastructure.cache import get_cache_backend
        cache = await get_cache_backend()
        
        if level and target_id:
            # 失效单个配置
            cache_key = f"{CONFIG_CACHE_PREFIX}{level}:{target_id}"
            await cache.delete(cache_key)
            logger.info(f"配置缓存已失效：{cache_key}")
        else:
            # 失效所有配置缓存
            patterns = [
                f"{CONFIG_CACHE_PREFIX}offer:*",
                f"{CONFIG_CACHE_PREFIX}publisher:*",
                f"{CONFIG_CACHE_PREFIX}advertiser:*"
            ]
            for pattern in patterns:
                await cache.delete_pattern(pattern)
            logger.info(f"所有配置缓存已失效")
