"""
Offer 信息 Redis 缓存模块。

职责：缓存 offer_id → advertiser_id 等热点字段，降低 Postback/Tracklink 链路中的 DB 查询。
含 TTL 抖动与空值短缓存，降低雪崩/穿透。
"""
import logging
import json
import random
from dataclasses import dataclass
from typing import Literal, Optional
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


@dataclass(frozen=True)
class OfferCacheEntry:
    """Offer 缓存读取结果，明确区分命中、负缓存、未命中和 Redis 故障。"""

    status: Literal["hit", "negative", "miss", "unavailable"]
    advertiser_id: Optional[int] = None


async def get_offer_cache_entry(offer_id: int) -> OfferCacheEntry:
    """读取 Offer 缓存并返回明确状态，避免把 Redis 故障误判为缓存未命中。"""
    try:
        redis = await get_redis_client()
    except Exception as exc:
        logger.warning(
            "获取 Redis 客户端失败，跳过 Offer 缓存读取: offer_id=%s error_type=%s",
            offer_id,
            type(exc).__name__,
        )
        return OfferCacheEntry(status="unavailable")

    if not redis:
        return OfferCacheEntry(status="unavailable")

    cache_key = f"{OFFER_CACHE_PREFIX}{offer_id}"
    try:
        cached_data = await redis.get(cache_key)
    except Exception as exc:
        logger.warning(
            "读取 Offer 缓存失败: offer_id=%s error_type=%s",
            offer_id,
            type(exc).__name__,
        )
        return OfferCacheEntry(status="unavailable")

    if cached_data is None:
        return OfferCacheEntry(status="miss")

    try:
        if isinstance(cached_data, bytes):
            cached_data = cached_data.decode("utf-8")
        if cached_data == NONE_MARKER:
            return OfferCacheEntry(status="negative")

        data = json.loads(cached_data)
        if not isinstance(data, dict):
            raise ValueError("Offer cache payload must be a JSON object")

        advertiser_id = data.get("advertiser_id")
        if advertiser_id is None:
            return OfferCacheEntry(status="negative")
        if isinstance(advertiser_id, bool) or not isinstance(advertiser_id, int):
            raise ValueError("Offer cache advertiser_id must be an integer")
        return OfferCacheEntry(status="hit", advertiser_id=advertiser_id)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError) as exc:
        # 仅将缓存载荷解析/校验错误视为未命中；Redis 读操作异常始终是 unavailable。
        try:
            await redis.delete(cache_key)
        except Exception:
            logger.debug("清理损坏的 Offer 缓存失败: offer_id=%s", offer_id)
        logger.warning(
            "Offer 缓存数据无效，按未命中处理: offer_id=%s error_type=%s",
            offer_id,
            type(exc).__name__,
        )
        return OfferCacheEntry(status="miss")


async def get_offer_advertiser_id(offer_id: int) -> Optional[int]:
    """兼容旧调用方：只返回有效 advertiser_id，其余状态仍返回 None。"""
    entry = await get_offer_cache_entry(offer_id)
    return entry.advertiser_id if entry.status == "hit" else None


async def set_offer_cache(
    offer_id: int,
    advertiser_id: Optional[int],
    offer_name: Optional[str] = None,
    add_tags: bool = True,
) -> bool:
    """缓存 Offer；Redis 故障只影响缓存，不影响数据库权威业务结果。"""
    try:
        redis = await get_redis_client()
        if not redis:
            return False

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
    """清除 Offer 缓存；Redis 客户端获取或删除失败均返回 False。"""
    try:
        redis = await get_redis_client()
        if not redis:
            return False

        await redis.delete(f"{OFFER_CACHE_PREFIX}{offer_id}")
        return True
    except Exception as e:
        logger.warning(
            "清除 Offer 缓存失败: offer_id=%s error_type=%s",
            offer_id,
            type(e).__name__,
        )
        return False
