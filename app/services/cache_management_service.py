"""
Redis 缓存管理后台服务。

功能说明：
- 供管理端 API 扫描、预览、删除 Redis 键；返回结构与前端 CacheManagement 页对齐
- 键类型推断见 ``_TYPE_RULES``：string 可预览，hash 序列化 JSON，list/set 仅展示长度

安全约束：
- ``csrf:`` / ``session:`` / ``rate_limit:`` 前缀为受保护键，禁止单删与批量删
- 按 pattern 删除时拒绝过宽模式（如 ``*``），且不可匹配受保护前缀

在系统中的位置：
- 仅管理员可访问；底层使用 ``app.core.redis_client``

注意事项：
1. 生产环境删除操作应二次确认，避免误删业务缓存导致雪崩
2. SCAN 大量键时可能阻塞 Redis，建议限制 count 与分页
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# 禁止通过管理 API 批量删除的前缀（安全敏感）
_PROTECTED_PREFIXES = (
    "csrf:",
    "session:",
    "rate_limit:",
)

# (键前缀, 前端展示类型) — 顺序优先匹配
_TYPE_RULES: Tuple[Tuple[str, str], ...] = (
    ("short_link:", "ShortLink"),
    ("query_cache:", "API"),
    ("offer:", "API"),
    ("publisher:", "API"),
    ("advertiser:", "API"),
    ("cpl:deduction_config:", "API"),
    ("cache_tag:", "System"),
    ("tag_keys:", "System"),
    ("cache:metrics:", "System"),
    ("csrf:", "System"),
    ("rate_limit:", "System"),
    ("clicks:queue", "Task"),
    ("cap:", "API"),
    ("cloak:", "Cloak"),
    ("user_stats", "User"),
)


def _infer_cache_type(key: str) -> str:
    """根据键名前缀推断缓存分类，供管理端分组展示。"""
    for prefix, cache_type in _TYPE_RULES:
        if key.startswith(prefix) or key == prefix.rstrip(":"):
            return cache_type
    if ":" in key:
        head = key.split(":", 1)[0]
        return head.replace("_", " ").title()
    return "Other"


def _comment_for_key(key: str) -> str:
    """生成人类可读的键说明（管理列表 comment 列）。"""
    if key.startswith("short_link:"):
        return f"短链缓存 {key.split(':', 1)[-1]}"
    if key.startswith("query_cache:"):
        return "查询结果缓存"
    if key.startswith("offer:"):
        return f"Offer 缓存 {key.split(':', 1)[-1]}"
    if key.startswith("publisher:"):
        return f"渠道缓存 {key.split(':', 1)[-1]}"
    if key.startswith("cpl:deduction_config:"):
        return "扣减配置缓存"
    if key.startswith("cache_tag:"):
        return "缓存标签索引"
    return key


def _is_protected_key(key: str) -> bool:
    """判断键是否属于受保护前缀，删除类 API 应拒绝。"""
    return any(key.startswith(p) for p in _PROTECTED_PREFIXES)


def _preview_value(raw: Any, max_len: int = 2000) -> Tuple[str, bool]:
    """
    将 Redis 原始值转为可展示字符串。

    Returns:
        (预览文本, 是否未截断可完整查看)
    """
    if raw is None:
        return "", False
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = repr(raw[:200])
    else:
        text = str(raw)
    can_view = len(text) <= max_len
    if len(text) > max_len:
        text = text[:max_len] + "…"
    return text, can_view


async def list_cache_entries(
    *,
    pattern: str = "*",
    limit: int = 200,
) -> Dict[str, Any]:
    """
    扫描 Redis 并返回缓存条目列表。

    使用 SCAN 迭代，最多返回 safe_limit 条；Redis 不可用时返回空列表并标记 redis_available=False。

    Args:
        pattern: SCAN 匹配模式，默认 *
        limit: 最大条数，钳制在 1–500

    Returns:
        items、total、redis_available
    """
    redis = await get_redis_client()
    if not redis:
        return {"items": [], "total": 0, "redis_available": False}

    safe_limit = max(1, min(limit, 500))
    keys: List[str] = []
    async for key in redis.scan_iter(match=pattern or "*", count=200):
        keys.append(key if isinstance(key, str) else key.decode("utf-8", errors="replace"))
        if len(keys) >= safe_limit:
            break

    keys.sort()
    items: List[Dict[str, Any]] = []
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 逐键读取 type/ttl/体量，按 Redis 数据类型组装预览
    for key in keys:
        try:
            key_type = await redis.type(key)
            if isinstance(key_type, bytes):
                key_type = key_type.decode("utf-8")
            ttl = await redis.ttl(key)
            expire_time: Optional[int] = None
            if ttl and ttl > 0:
                expire_time = now_ms + ttl * 1000

            size = 0
            content = ""
            can_view = True
            if key_type == "string":
                raw = await redis.get(key)
                if raw is not None:
                    size = len(raw) if isinstance(raw, (bytes, bytearray)) else len(str(raw))
                    content, can_view = _preview_value(raw)
            elif key_type == "hash":
                raw_map = await redis.hgetall(key)
                text = json.dumps(
                    {
                        (k.decode() if isinstance(k, bytes) else k): (
                            v.decode() if isinstance(v, bytes) else v
                        )
                        for k, v in (raw_map or {}).items()
                    },
                    ensure_ascii=False,
                )
                size = len(text.encode("utf-8"))
                content, can_view = _preview_value(text)
            elif key_type == "list":
                length = await redis.llen(key)
                size = length
                content = f"[list length={length}]"
                can_view = False
            elif key_type == "set":
                length = await redis.scard(key)
                size = length
                content = f"[set size={length}]"
                can_view = False
            else:
                content = f"[{key_type}]"
                can_view = False

            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            items.append(
                {
                    "key": key,
                    "comment": _comment_for_key(key),
                    "size": size,
                    "expireTime": expire_time,
                    "type": _infer_cache_type(key),
                    "hits": 0,
                    "createdAt": ts,
                    "updatedAt": ts,
                    "content": content,
                    "canView": can_view and key_type == "string",
                    "protected": _is_protected_key(key),
                }
            )
        except Exception as exc:
            logger.warning("读取缓存键失败: %s (%s)", key, exc)

    return {"items": items, "total": len(items), "redis_available": True}


async def get_cache_entry(key: str) -> Optional[Dict[str, Any]]:
    """
    读取单条缓存详情。

    string 类型在列表预览基础上放宽至约 50KB 完整内容；其他类型与 list 条目一致。

    Args:
        key: Redis 键名

    Returns:
        条目字典；键不存在或 Redis 不可用则 None
    """
    redis = await get_redis_client()
    if not redis:
        return None
    exists = await redis.exists(key)
    if not exists:
        return None

    listing = await list_cache_entries(pattern=key, limit=500)
    base = next((i for i in listing["items"] if i["key"] == key), None)
    if not base:
        return None

    key_type = await redis.type(key)
    if isinstance(key_type, bytes):
        key_type = key_type.decode("utf-8")
    if key_type == "string":
        raw = await redis.get(key)
        content, _ = _preview_value(raw, max_len=50000)
        return {**base, "content": content, "canView": True}
    return base


async def delete_cache_entry(key: str) -> bool:
    """
    删除单条缓存。

    Args:
        key: Redis 键名

    Returns:
        是否实际删除了键

    Raises:
        ValueError: 受保护前缀
    """
    if _is_protected_key(key):
        raise ValueError(f"受保护的缓存键不可删除: {key}")
    redis = await get_redis_client()
    if not redis:
        return False
    deleted = await redis.delete(key)
    return bool(deleted)


async def clear_all_cache_entries() -> int:
    """
    清空全部非受保护缓存键（SCAN * 逐删）。

    Returns:
        删除的键数量；Redis 不可用时为 0
    """
    redis = await get_redis_client()
    if not redis:
        return 0

    deleted = 0
    async for key in redis.scan_iter(match="*", count=200):
        key_str = key if isinstance(key, str) else key.decode("utf-8", errors="replace")
        if _is_protected_key(key_str):
            continue
        deleted += await redis.delete(key_str)
    return deleted


async def delete_cache_by_pattern(pattern: str) -> int:
    """
    按 SCAN pattern 批量删除非受保护键。

    拒绝 *、过短通配及会命中受保护前缀的 pattern。

    Args:
        pattern: Redis SCAN 模式，须足够具体

    Returns:
        删除的键数量

    Raises:
        ValueError: pattern 过宽或触及受保护前缀
    """
    if pattern in ("*", "") or pattern.endswith("*") and len(pattern) <= 2:
        raise ValueError("拒绝过宽的模式，请指定更具体的 pattern")
    if any(p.strip("*") in pattern for p in _PROTECTED_PREFIXES):
        raise ValueError("pattern 不可匹配受保护前缀")

    redis = await get_redis_client()
    if not redis:
        return 0

    deleted = 0
    async for key in redis.scan_iter(match=pattern, count=200):
        key_str = key if isinstance(key, str) else key.decode("utf-8", errors="replace")
        if _is_protected_key(key_str):
            continue
        deleted += await redis.delete(key_str)
    return deleted
