"""
广告数据查询缓存键与失效。

筛选项（products/clients with-data）、KPI summary、每日汇总 daily-summary
使用 Redis（query_cache: 命名空间）。
键格式带可读前缀，便于入库后按前缀批量失效；避免仅 MD5 时无法定向清理。
冷路径通过 ``ad_data_get_or_set`` 做进程内单飞 + 跨 Worker 锁等待，减轻缓存击穿。
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from app.core.infrastructure.cache_compat import (
    generate_cache_key,
    get_or_set_single_flight,
    invalidate_cache,
)

logger = logging.getLogger(__name__)

AD_DATA_QUERY_CACHE_NS = "ad_data"


def ad_data_daily_summary_cache_ttl() -> int:
    """每日汇总列表 + 全量合计缓存 TTL（秒）。"""
    from app.core.config import settings

    return int(getattr(settings, "AD_DATA_DAILY_SUMMARY_CACHE_TTL", 600))


def ad_data_filter_options_cache_ttl() -> int:
    """筛选项（products-with-data 等）缓存 TTL（秒）。"""
    from app.core.config import settings

    return int(getattr(settings, "AD_DATA_FILTER_OPTIONS_CACHE_TTL", 600))


def ad_data_summary_cache_ttl() -> int:
    """KPI summary / dashboard 汇总缓存 TTL（秒）。"""
    from app.core.config import settings

    return int(getattr(settings, "AD_DATA_SUMMARY_CACHE_TTL", 300))


def build_ad_data_query_cache_key(kind: str, *parts) -> str:
    """生成 ``ad_data:{kind}:{md5}`` 形式的查询缓存键（不含 query_cache: 前缀）。"""
    digest = generate_cache_key(kind, *parts)
    safe_kind = str(kind or "misc").strip() or "misc"
    return f"{AD_DATA_QUERY_CACHE_NS}:{safe_kind}:{digest}"


async def invalidate_ad_data_query_caches(*, reason: str = "") -> int:
    """
    清除广告数据相关查询缓存（筛选项 + 汇总等）。

    入库/更新/删除广告或新建产品后应调用，避免管理端下拉仍显示旧产品列表。
    """
    deleted = await invalidate_cache(f"{AD_DATA_QUERY_CACHE_NS}:")
    if deleted:
        logger.info(
            "已失效广告数据查询缓存: deleted=%s reason=%s",
            deleted,
            reason or "-",
        )
    else:
        logger.debug(
            "广告数据查询缓存无需清理或已为空: reason=%s",
            reason or "-",
        )
    return deleted


async def ad_data_get_or_set(
    cache_key: str,
    factory: Callable[[], Awaitable[Any]],
    *,
    ttl: int,
    is_valid: Optional[Callable[[Any], bool]] = None,
    wait_timeout: float = 25.0,
) -> Any:
    """广告数据查询缓存：未命中时单飞计算并写回（metric 前缀 ad_data）。"""
    return await get_or_set_single_flight(
        cache_key,
        factory,
        ttl=ttl,
        key_prefix="ad_data",
        is_valid=is_valid,
        wait_timeout=wait_timeout,
    )
