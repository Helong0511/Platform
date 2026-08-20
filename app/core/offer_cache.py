"""
Offer 信息 Redis 缓存模块。

职责：缓存 offer_id → advertiser_id 等热点字段，降低 Postback/Tracklink 链路中的 DB 查询。
含 TTL 抖动与空值短缓存，降低雪崩/穿透。
"""
import logging
import json
import random
from typing import Optional
from datetime import datetime, timezone
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

OFFER_CACHE_PREFIX = "offer:cache:"
CACHE_TTL = 3600
NONE_MARKER = "__none__"
NONE_TTL = 60


def _ttl_with_jitter(base: int = CACHE_TTL, jitter_max: int = 300) -> int:
    """基础 TTL + [1, jitter_max] 随机抖动，防雪崩。"""
    return max(1, int(base) + random.randint(1, max(1, jitter_max)))


async def get_offer_advertiser_id(offer_id: int) -> Optional[int]:
    """从缓存获取 Offer 的 advertiser_id；命中空值标记返回 None。"""
    redis = await get_redis_client()
    if not redis:
        return None

    try:
        cache_key = f"{OFFER_CACHE_PREFIX}{offer_id}"
        cached_data = await redis.get(cache_key)
        if not cached_data:
            return None
        if isinstance(cached_data, bytes):
            cached_data = cached_data.decode("utf-8")
        if cached_data == NONE_MARKER:
            return None
        data = json.loads(cached_data)
        return data.get("advertiser_id")
    except Exception as e:
        logger.debug(f"从缓存获取Offer信息失败: offer_id={offer_id}, error={e}")

    return None


async def set_offer_cache(
    offer_id: int,
    advertiser_id: Optional[int],
    offer_name: Optional[str] = None,
    add_tags: bool = True,
) -> bool:
    """缓存 Offer；advertiser_id 为 None 时写入短 TTL 空值标记。"""
    redis = await get_redis_client()
    if not redis:
        return False

    try:
        cache_key = f"{OFFER_CACHE_PREFIX}{offer_id}"
        if advertiser_id is None:
            await redis.setex(cache_key, NONE_TTL, NONE_MARKER)
            return True

        data = {
            "offer_id": offer_id,
            "advertiser_id": advertiser_id,
            "offer_name": offer_name,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        await redis.setex(cache_key, _ttl_with_jitter(), json.dumps(data, default=str))

        if add_tags:
            try:
                from app.core.cache_manager import CacheManager

                tags = [f"offer:{offer_id}", f"advertiser:{advertiser_id}"]
                await CacheManager.add_cache_tag(cache_key, tags)
            except Exception as tag_error:
                logger.debug(f"添加缓存标签失败: {tag_error}，不影响缓存写入")

        return True
    except Exception as e:
        logger.debug(f"缓存Offer信息失败: offer_id={offer_id}, error={e}")
        return False


async def invalidate_offer_cache(offer_id: int) -> bool:
    """清除 Offer 缓存。"""
    redis = await get_redis_client()
    if not redis:
        return False

    try:
        await redis.delete(f"{OFFER_CACHE_PREFIX}{offer_id}")
        return True
    except Exception as e:
        logger.debug(f"清除Offer缓存失败: offer_id={offer_id}, error={e}")
        return False
