"""
性能优化方案 / 瓶颈记录的 Redis 持久化（多 Worker 共享）。

Redis 键:
    - ``platform:optimization:plans``：Hash，field=方案 ID，value=JSON
    - ``platform:optimization:bottlenecks``：List，最近 N 条瓶颈 JSON

Redis 不可用时回退为进程内内存（与改造前行为一致），读写失败不阻断业务。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_PLANS_HASH_KEY = "platform:optimization:plans"
_BOTTLENECKS_LIST_KEY = "platform:optimization:bottlenecks"
_MAX_BOTTLENECKS = 1000


async def load_plans_from_redis() -> Dict[str, Dict[str, Any]]:
    """
    从 Redis 加载全部优化方案。

    Returns:
        ``{plan_id: plan_dict}``；Redis 不可用或读取失败时返回空 dict。

    异常:
        捕获所有异常并记 warning，不向上抛出。
    """
    try:
        from app.core.redis_client import get_redis_client

        client = await get_redis_client()
        if not client:
            return {}
        raw = await client.hgetall(_PLANS_HASH_KEY)
        return {plan_id: json.loads(payload) for plan_id, payload in raw.items()}
    except Exception as exc:
        logger.warning("优化方案 Redis 读取失败，使用进程内缓存: %s", exc)
        return {}


async def save_plan_to_redis(plan_id: str, plan_dict: Dict[str, Any]) -> None:
    """
    将单条优化方案写入 Redis Hash。

    Args:
        plan_id: 方案唯一 ID。
        plan_dict: ``OptimizationPlan.to_dict()`` 序列化结果。

    副作用:
        HSET ``platform:optimization:plans``；Redis 不可用时无操作。

    异常:
        捕获所有异常并记 debug，不向上抛出。
    """
    try:
        from app.core.redis_client import get_redis_client

        client = await get_redis_client()
        if not client:
            return
        await client.hset(_PLANS_HASH_KEY, plan_id, json.dumps(plan_dict, ensure_ascii=False))
    except Exception as exc:
        logger.debug("优化方案 Redis 写入跳过: %s", exc)


async def delete_plan_from_redis(plan_id: str) -> None:
    """
    从 Redis 删除指定优化方案。

    Args:
        plan_id: 要删除的方案 ID。

    副作用:
        HDEL ``platform:optimization:plans``；Redis 不可用时无操作。

    异常:
        捕获所有异常并记 debug，不向上抛出。
    """
    try:
        from app.core.redis_client import get_redis_client

        client = await get_redis_client()
        if not client:
            return
        await client.hdel(_PLANS_HASH_KEY, plan_id)
    except Exception as exc:
        logger.debug("优化方案 Redis 删除跳过: %s", exc)


async def load_bottlenecks_from_redis(limit: int = _MAX_BOTTLENECKS) -> List[Dict[str, Any]]:
    """
    从 Redis 加载最近若干条瓶颈记录。

    Args:
        limit: 最多返回条数，对应 LRANGE 尾部窗口，默认 1000。

    Returns:
        瓶颈 dict 列表（时间顺序）；Redis 不可用或失败时返回空 list。

    异常:
        捕获所有异常并记 warning，不向上抛出。
    """
    try:
        from app.core.redis_client import get_redis_client

        client = await get_redis_client()
        if not client:
            return []
        items = await client.lrange(_BOTTLENECKS_LIST_KEY, -limit, -1)
        return [json.loads(item) for item in items]
    except Exception as exc:
        logger.warning("瓶颈记录 Redis 读取失败: %s", exc)
        return []


async def append_bottleneck_to_redis(record_dict: Dict[str, Any]) -> None:
    """
    追加一条瓶颈记录并裁剪列表长度。

    Args:
        record_dict: ``BottleneckRecord.to_dict()`` 序列化结果。

    副作用:
        RPUSH + LTRIM 保持列表最多 ``_MAX_BOTTLENECKS`` 条；Redis 不可用时无操作。

    异常:
        捕获所有异常并记 debug，不向上抛出。
    """
    try:
        from app.core.redis_client import get_redis_client

        client = await get_redis_client()
        if not client:
            return
        pipe = client.pipeline()
        pipe.rpush(_BOTTLENECKS_LIST_KEY, json.dumps(record_dict, ensure_ascii=False))
        pipe.ltrim(_BOTTLENECKS_LIST_KEY, -_MAX_BOTTLENECKS, -1)
        await pipe.execute()
    except Exception as exc:
        logger.debug("瓶颈记录 Redis 写入跳过: %s", exc)
