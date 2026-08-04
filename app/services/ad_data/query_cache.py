"""
广告数据查询缓存键与失效。

筛选项（products/clients with-data）与 KPI summary 使用 Redis（query_cache: 命名空间）。
键格式带可读前缀，便于入库后按前缀批量失效；避免仅 MD5 时无法定向清理。
"""
from __future__ import annotations

import logging

from app.core.infrastructure.cache_compat import generate_cache_key, invalidate_cache

logger = logging.getLogger(__name__)

AD_DATA_QUERY_CACHE_NS = "ad_data"


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
