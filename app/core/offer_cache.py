"""
Offer信息缓存模块（高并发优化）
缓存Offer的advertiser_id映射，减少数据库查询
"""
import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Redis缓存键前缀
OFFER_CACHE_PREFIX = "offer:cache:"
# 缓存TTL：1小时（Offer信息变化不频繁）
CACHE_TTL = 3600


async def get_offer_advertiser_id(offer_id: int) -> Optional[int]:
    """
    从缓存获取Offer的advertiser_id
    
    Args:
        offer_id: Offer ID
        
    Returns:
        advertiser_id，如果不存在则返回None
    """
    redis = await get_redis_client()
    if not redis:
        return None
    
    try:
        cache_key = f"{OFFER_CACHE_PREFIX}{offer_id}"
        cached_data = await redis.get(cache_key)
        if cached_data:
            data = json.loads(cached_data)
            return data.get("advertiser_id")
    except Exception as e:
        logger.debug(f"从缓存获取Offer信息失败: offer_id={offer_id}, error={e}")
    
    return None


async def set_offer_cache(offer_id: int, advertiser_id: int, offer_name: Optional[str] = None, add_tags: bool = True) -> bool:
    """
    缓存Offer信息
    
    Args:
        offer_id: Offer ID
        advertiser_id: 广告主ID
        offer_name: Offer名称（可选）
        add_tags: 是否添加缓存标签（用于精确失效）
        
    Returns:
        是否设置成功
    """
    redis = await get_redis_client()
    if not redis:
        return False
    
    try:
        cache_key = f"{OFFER_CACHE_PREFIX}{offer_id}"
        data = {
            "offer_id": offer_id,
            "advertiser_id": advertiser_id,
            "offer_name": offer_name,
            "cached_at": datetime.now(timezone.utc).isoformat()
        }
        data_str = json.dumps(data, default=str)
        await redis.setex(cache_key, CACHE_TTL, data_str)
        
        # 添加缓存标签（用于精确失效）
        if add_tags:
            try:
                # 延迟导入，避免循环导入
                from app.core.cache_manager import CacheManager
                
                tags = [f"offer:{offer_id}"]
                if advertiser_id:
                    tags.append(f"advertiser:{advertiser_id}")
                await CacheManager.add_cache_tag(cache_key, tags)
            except Exception as tag_error:
                logger.debug(f"添加缓存标签失败: {tag_error}，不影响缓存写入")
        
        return True
    except Exception as e:
        logger.debug(f"缓存Offer信息失败: offer_id={offer_id}, error={e}")
        return False


async def invalidate_offer_cache(offer_id: int) -> bool:
    """
    清除Offer缓存（当Offer被更新时）
    
    Args:
        offer_id: Offer ID
        
    Returns:
        是否清除成功
    """
    redis = await get_redis_client()
    if not redis:
        return False
    
    try:
        cache_key = f"{OFFER_CACHE_PREFIX}{offer_id}"
        await redis.delete(cache_key)
        return True
    except Exception as e:
        logger.debug(f"清除Offer缓存失败: offer_id={offer_id}, error={e}")
        return False

