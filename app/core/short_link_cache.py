"""
短链接缓存模块
使用Redis缓存短链接数据，减少数据库查询，提高高并发性能
"""
import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# 缓存键前缀
CACHE_PREFIX = "short_link:"
# 缓存TTL：1小时（短链接数据变化不频繁）
CACHE_TTL = 3600


async def get_short_link_from_cache(short_code: str) -> Optional[Dict[str, Any]]:
    """
    从缓存获取短链接数据
    
    Args:
        short_code: 短链接代码
        
    Returns:
        短链接数据字典，如果不存在则返回None
    """
    redis = await get_redis_client()
    if not redis:
        return None
    
    try:
        cache_key = f"{CACHE_PREFIX}{short_code}"
        cached_data = await redis.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
    except Exception as e:
        logger.debug(f"从缓存获取短链接失败: {e}")
    return None


async def set_short_link_to_cache(short_code: str, short_link_data: Dict[str, Any], ttl: int = CACHE_TTL, add_tags: bool = True) -> bool:
    """
    将短链接数据写入缓存
    
    Args:
        short_code: 短链接代码
        short_link_data: 短链接数据字典
        ttl: 缓存过期时间（秒）
        add_tags: 是否添加缓存标签（用于精确失效）
        
    Returns:
        是否设置成功
    """
    redis = await get_redis_client()
    if not redis:
        return False
    
    try:
        cache_key = f"{CACHE_PREFIX}{short_code}"
        # 序列化数据
        data_str = json.dumps(short_link_data, default=str)
        await redis.setex(cache_key, ttl, data_str)
        
        # 添加缓存标签（用于精确失效）
        if add_tags:
            try:
                # 延迟导入，避免循环导入
                from app.core.cache_manager import CacheManager
                
                tags = [f"short_link:{short_code}"]
                # 如果有offer_id，添加offer标签
                if short_link_data.get("offer_id"):
                    tags.append(f"offer:{short_link_data['offer_id']}")
                # 如果有channel_id，添加channel标签
                if short_link_data.get("channel_id"):
                    tags.append(f"channel:{short_link_data['channel_id']}")
                await CacheManager.add_cache_tag(cache_key, tags)
            except Exception as tag_error:
                logger.debug(f"添加缓存标签失败: {tag_error}，不影响缓存写入")
        
        return True
    except Exception as e:
        logger.debug(f"写入短链接缓存失败: {e}")
    return False


async def invalidate_short_link_cache(short_code: str) -> bool:
    """
    清除短链接缓存（当短链接被更新或删除时）
    
    Args:
        short_code: 短链接代码
        
    Returns:
        是否清除成功
    """
    redis = await get_redis_client()
    if not redis:
        return False
    
    try:
        cache_key = f"{CACHE_PREFIX}{short_code}"
        await redis.delete(cache_key)
        return True
    except Exception as e:
        logger.debug(f"清除短链接缓存失败: {e}")
    return False


def serialize_short_link(short_link) -> Dict[str, Any]:
    """
    序列化短链接对象为字典
    
    Args:
        short_link: ShortLink模型实例
        
    Returns:
        序列化后的字典
    """
    return {
        "id": short_link.id,
        "short_code": short_link.short_code,
        "original_url": short_link.original_url,
        "is_active": short_link.is_active,
        "expires_at": short_link.expires_at.isoformat() if short_link.expires_at else None,
        "click_count": short_link.click_count,
        "show_count": short_link.show_count,
        "offer_id": short_link.offer_id,
        "channel_id": short_link.channel_id,
    }

