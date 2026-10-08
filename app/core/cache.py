"""
查询结果缓存 — 兼容垫片。

实际实现已迁移至 ``app.core.infrastructure.cache_compat``，
本模块保留 ``query_cache:`` 键命名空间与原有 import 路径。
"""
from app.core.infrastructure.cache_compat import (
    CACHE_PREFIX,
    DEFAULT_TTL,
    cache_query,
    clear_all_cache,
    generate_cache_key,
    get_or_set_cache,
    get_or_set_single_flight,
    invalidate_cache,
    legacy_get_cached as get_cached,
    legacy_set_cached as set_cached,
)

__all__ = [
    "CACHE_PREFIX",
    "DEFAULT_TTL",
    "generate_cache_key",
    "get_cached",
    "set_cached",
    "invalidate_cache",
    "cache_query",
    "clear_all_cache",
    "get_or_set_cache",
    "get_or_set_single_flight",
]
