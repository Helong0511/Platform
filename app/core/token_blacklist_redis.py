"""
JWT Redis 黑名单。

注销 / 改密 / 刷新轮换时将 jti 写入 Redis（TTL=剩余有效期），
校验 Token 时优先查 Redis，降低对 MySQL TokenBlacklist 的依赖延迟。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.redis_client import get_redis_client
from app.core.utils import get_app_now_naive, APP_TIMEZONE

logger = logging.getLogger(__name__)

_KEY_PREFIX = "jwt:blacklist:"


def _ttl_seconds_until(expires_at: datetime) -> int:
    """计算距过期的秒数（至少 1 秒）。"""
    now = get_app_now_naive()
    if expires_at.tzinfo is not None:
        expires_naive = expires_at.astimezone(APP_TIMEZONE).replace(tzinfo=None)
    else:
        expires_naive = expires_at
    delta = (expires_naive - now).total_seconds()
    return max(1, int(delta))


async def add_jti_to_redis_blacklist(
    jti: str,
    expires_at: datetime,
    reason: str = "",
) -> bool:
    """
    将 jti 写入 Redis 黑名单，TTL 等于 Token 剩余有效时间。

    Returns:
        是否写入成功（Redis 不可用时返回 False，调用方仍应写 MySQL）
    """
    if not jti:
        return False
    redis = await get_redis_client()
    if not redis:
        return False
    try:
        ttl = _ttl_seconds_until(expires_at)
        key = f"{_KEY_PREFIX}{jti}"
        await redis.setex(key, ttl, reason or "revoked")
        return True
    except Exception as exc:
        logger.warning("写入 JWT Redis 黑名单失败: jti=%s error=%s", jti[:12], exc)
        return False


async def is_jti_redis_blacklisted(jti: str) -> bool:
    """查询 jti 是否在 Redis 黑名单中。Redis 不可用时返回 False（回退 MySQL）。"""
    if not jti:
        return False
    redis = await get_redis_client()
    if not redis:
        return False
    try:
        return bool(await redis.exists(f"{_KEY_PREFIX}{jti}"))
    except Exception as exc:
        logger.debug("查询 JWT Redis 黑名单失败: %s", exc)
        return False
