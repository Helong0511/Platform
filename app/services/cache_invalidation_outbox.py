"""广告数据查询缓存 Generation 与事务性失效事件登记。

业务 Service 必须在修改业务数据的同一个 AsyncSession 事务内调用
advance_cache_generation()；本模块绝不自行 commit/rollback。
"""
from __future__ import annotations

import hashlib
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import get_app_now_sql_expression
from app.models.models import CacheInvalidationOutbox, CacheNamespaceGeneration

AD_DATA_CACHE_NAMESPACE = "ad_data"


class CacheGenerationUnavailable(RuntimeError):
    """数据库权威 Generation 缺失或无法读取时 fail closed。"""


async def get_cache_generation(
    db: AsyncSession,
    namespace: str = AD_DATA_CACHE_NAMESPACE,
) -> int:
    """从当前业务事务读取版本，保证版本与该事务的数据可见性一致。"""
    generation = await db.scalar(
        select(CacheNamespaceGeneration.generation).where(
            CacheNamespaceGeneration.namespace == namespace
        )
    )
    if generation is None or int(generation) < 1:
        raise CacheGenerationUnavailable(
            f"cache generation is unavailable for namespace={namespace}"
        )
    return int(generation)


async def get_cache_generations(
    db: AsyncSession,
    namespaces: Iterable[str],
) -> dict[str, int]:
    """在一个数据库查询中读取多个权威缓存版本；缺失时 fail closed。"""
    normalized = tuple(dict.fromkeys(namespaces))
    if not normalized:
        return {}

    result = await db.execute(
        select(
            CacheNamespaceGeneration.namespace,
            CacheNamespaceGeneration.generation,
        ).where(CacheNamespaceGeneration.namespace.in_(normalized))
    )
    generations = {
        str(namespace): int(generation)
        for namespace, generation in result.all()
        if generation is not None and int(generation) > 0
    }
    missing = [namespace for namespace in normalized if namespace not in generations]
    if missing:
        raise CacheGenerationUnavailable(
            "cache generation is unavailable for namespaces="
            + ",".join(missing)
        )
    return {namespace: generations[namespace] for namespace in normalized}


async def advance_cache_generation(
    db: AsyncSession,
    *,
    namespace: str = AD_DATA_CACHE_NAMESPACE,
) -> int:
    """原子递增版本并登记 Outbox；调用方负责提交业务事务。

    对应迁移必须预置该命名空间单例行。UPDATE 锁定该行并串行化同一命名空间
    的并发变更；Outbox event_key 唯一约束防止重复登记。
    """
    result = await db.execute(
        update(CacheNamespaceGeneration)
        .where(CacheNamespaceGeneration.namespace == namespace)
        .values(generation=CacheNamespaceGeneration.generation + 1)
    )
    if (result.rowcount or 0) != 1:
        raise CacheGenerationUnavailable(
            f"cache generation row missing for namespace={namespace}"
        )

    generation = await get_cache_generation(db, namespace)
    event_key = hashlib.sha256(
        f"{namespace}:{generation}".encode("utf-8")
    ).hexdigest()
    db.add(
        CacheInvalidationOutbox(
            event_key=event_key,
            namespace=namespace,
            generation=generation,
            status="pending",
            attempt_count=0,
            max_attempts=12,
            next_retry_time=get_app_now_sql_expression(),
        )
    )
    await db.flush()
    return generation
