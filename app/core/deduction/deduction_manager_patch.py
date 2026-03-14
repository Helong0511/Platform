"""
扣量管理器缓存修复补丁

使用方法：
1. 备份原文件：cp deduction_manager.py deduction_manager.py.bak
2. 找到 _get_cached_config 和 _cache_config 方法
3. 用本文件中的代码替换
"""

# ====== 替换 _get_cached_config 方法 ======
async def _get_cached_config(
    self,
    level: str,
    target_id: int
) -> Optional[ConversionDeductionConfig]:
    """从缓存获取配置（已修复序列化问题）"""
    from app.core.infrastructure.cache_compat import get_cached
    
    cache_key = f"{CONFIG_CACHE_PREFIX}{level}:{target_id}"
    cached_data = await get_cached(cache_key, key_prefix='deduction')
    
    if cached_data and isinstance(cached_data, dict):
        try:
            # 从缓存字典重建配置对象
            config = ConversionDeductionConfig(
                id=cached_data.get('id'),
                offer_id=cached_data.get('offer_id'),
                publisher_id=cached_data.get('publisher_id'),
                advertiser_id=cached_data.get('advertiser_id'),
                volume_deduction_ratio=float(cached_data.get('volume_deduction_ratio', 0)),
                amount_deduction_ratio=float(cached_data.get('amount_deduction_ratio', 0)),
                priority=int(cached_data.get('priority', 0)),
                is_active=bool(cached_data.get('is_active', True)),
                strategy=cached_data.get('strategy', 'random'),
                created_at=cached_data.get('created_at'),
                updated_at=cached_data.get('updated_at')
            )
            logger.debug(f"缓存命中：deduction_config:{level}:{target_id}")
            return config
        except Exception as e:
            logger.warning(f"从缓存重建配置失败：{e}")
            return None
    
    return None


# ====== 替换 _cache_config 方法 ======
async def _cache_config(
    self,
    level: str,
    target_id: int,
    config: ConversionDeductionConfig
) -> None:
    """缓存配置（已修复序列化问题）"""
    from app.core.infrastructure.cache_compat import set_cached
    
    cache_key = f"{CONFIG_CACHE_PREFIX}{level}:{target_id}"
    
    # 序列化为字典（避免 SQLAlchemy 对象序列化问题）
    config_dict = {
        'id': config.id,
        'offer_id': config.offer_id,
        'publisher_id': config.publisher_id,
        'advertiser_id': config.advertiser_id,
        'volume_deduction_ratio': config.volume_deduction_ratio,
        'amount_deduction_ratio': config.amount_deduction_ratio,
        'priority': config.priority,
        'is_active': config.is_active,
        'strategy': config.strategy,
        'created_at': str(config.created_at) if config.created_at else None,
        'updated_at': str(config.updated_at) if config.updated_at else None
    }
    
    await set_cached(cache_key, config_dict, ttl=CONFIG_CACHE_TTL, key_prefix='deduction')
    logger.debug(f"配置已缓存：deduction_config:{level}:{target_id}, TTL={CONFIG_CACHE_TTL}s")


# ====== 新增：缓存失效方法 ======
async def invalidate_deduction_config(
    self,
    offer_id: int = None,
    publisher_id: int = None,
    advertiser_id: int = None
):
    """失效扣量配置缓存"""
    from app.core.infrastructure.cache import get_cache_backend
    
    cache = await get_cache_backend()
    
    if offer_id:
        await cache.delete_pattern(f"{CONFIG_CACHE_PREFIX}offer:{offer_id}*")
        logger.info(f"Offer 配置缓存已失效：offer_id={offer_id}")
    
    if publisher_id:
        await cache.delete_pattern(f"{CONFIG_CACHE_PREFIX}publisher:{publisher_id}*")
        logger.info(f"Publisher 配置缓存已失效：publisher_id={publisher_id}")
    
    if advertiser_id:
        await cache.delete_pattern(f"{CONFIG_CACHE_PREFIX}advertiser:{advertiser_id}*")
        logger.info(f"Advertiser 配置缓存已失效：advertiser_id={advertiser_id}")
