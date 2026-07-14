"""
跨 Gunicorn Worker 的监控指标 Redis 聚合。

各 Worker 将 API 请求计数写入 Redis 分钟桶；本模块负责汇总并供
``SystemMonitor.get_api_stats()`` 通过 ``apply_redis_api_totals`` 替换本进程重复计数。

Redis 不可用时静默降级，不影响主请求路径。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Redis Hash 键前缀：platform:monitor:api:YYYYMMDDHHMM
_KEY_PREFIX = "platform:monitor:api:"
# 分钟桶 TTL（秒），保留约 24 小时供汇总窗口读取
_TTL_SECONDS = 86400

# 最近一次 refresh_api_totals_cache 的跨 Worker 汇总（进程内缓存）
_redis_totals_cache: Dict[str, float] = {}
_redis_cache_lock = Lock()


def _minute_bucket(when: Optional[datetime] = None) -> str:
    """
    生成 UTC 分钟桶后缀，用于 Redis 键名。

    Args:
        when: 指定时刻；默认当前 UTC 时间。

    Returns:
        格式 ``YYYYMMDDHHMM`` 的字符串。
    """
    ts = when or datetime.now(timezone.utc)
    return ts.strftime("%Y%m%d%H%M")


async def record_api_request_async(
    *,
    status_code: int,
    duration: float,
    slow: bool,
    very_slow: bool,
) -> None:
    """
    将单条 API 请求计数写入当前分钟 Redis Hash（供多 Worker 汇总）。

    Args:
        status_code: HTTP 响应状态码；仅 >=500 时递增 error_count（与进程内监控一致）。
        duration: 请求耗时（秒），累加至 total_duration。
        slow: 是否达到慢请求阈值。
        very_slow: 是否达到极慢请求阈值。

    副作用:
        对当前分钟桶执行 HINCRBY / HINCRBYFLOAT；键过期时间为 ``_TTL_SECONDS``。

    异常:
        任意 Redis 错误均被捕获并记 debug 日志，不向上抛出。
    """
    try:
        from app.core.redis_client import get_redis_client
        from app.core.monitoring import is_monitored_error_status

        client = await get_redis_client()
        if not client:
            return

        key = f"{_KEY_PREFIX}{_minute_bucket()}"
        pipe = client.pipeline()
        pipe.hincrby(key, "request_count", 1)
        pipe.hincrbyfloat(key, "total_duration", float(duration))
        if is_monitored_error_status(status_code):
            pipe.hincrby(key, "error_count", 1)
        if slow:
            pipe.hincrby(key, "slow_request_count", 1)
        if very_slow:
            pipe.hincrby(key, "very_slow_request_count", 1)
        pipe.expire(key, _TTL_SECONDS)
        await pipe.execute()
    except Exception as exc:
        logger.debug("监控 Redis 写入跳过: %s", exc)


async def refresh_api_totals_cache(retention_hours: int = 24) -> None:
    """
    拉取 retention 窗口内各 Worker 写入的 Redis 分钟桶并更新进程内缓存。

    Args:
        retention_hours: 回溯小时数，转换为分钟桶数量（至少 1 分钟）。

    副作用:
        成功时更新 ``_redis_totals_cache``；Redis 不可用时清空缓存。

    异常:
        Redis 读取失败时记 debug 日志并保留旧缓存不变。
    """
    totals = {
        "request_count": 0,
        "error_count": 0,
        "total_duration": 0.0,
        "slow_request_count": 0,
        "very_slow_request_count": 0,
    }
    try:
        from app.core.redis_client import get_redis_client

        client = await get_redis_client()
        if not client:
            with _redis_cache_lock:
                _redis_totals_cache.clear()
            return

        now = datetime.now(timezone.utc)
        minutes = max(1, int(retention_hours * 60))
        keys = [
            f"{_KEY_PREFIX}{(now - timedelta(minutes=offset)).strftime('%Y%m%d%H%M')}"
            for offset in range(minutes)
        ]
        if not keys:
            return

        for key in keys:
            data = await client.hgetall(key)
            if not data:
                continue
            totals["request_count"] += int(float(data.get("request_count", 0)))
            totals["error_count"] += int(float(data.get("error_count", 0)))
            totals["total_duration"] += float(data.get("total_duration", 0))
            totals["slow_request_count"] += int(float(data.get("slow_request_count", 0)))
            totals["very_slow_request_count"] += int(
                float(data.get("very_slow_request_count", 0))
            )
    except Exception as exc:
        logger.debug("监控 Redis 读取跳过: %s", exc)
        return

    with _redis_cache_lock:
        _redis_totals_cache.clear()
        _redis_totals_cache.update(totals)


def get_cached_redis_api_totals() -> Dict[str, float]:
    """
    读取最近一次 ``refresh_api_totals_cache`` 的跨 Worker 汇总。

    Returns:
        含 request_count、error_count、total_duration 等字段的字典副本；
        未刷新或 Redis 不可用时可能为空 dict。
    """
    with _redis_cache_lock:
        return dict(_redis_totals_cache)


def apply_redis_api_totals(local_stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    当 Redis 有跨 Worker 汇总时，用其替换本进程 API 聚合计数。

    行为说明:
        - Redis 缓存有效且 request_count > 0：返回新 dict，计数类字段来自 Redis，
          避免多 Worker 各自累加后仪表盘重复计数。
        - 否则：原样返回 ``local_stats``（单 Worker 或 Redis 降级）。
        - 百分位、慢请求明细列表仍来自本进程样本（近似值，非全局精确）。

    Args:
        local_stats: ``SystemMonitor`` 本进程聚合的 API 统计 dict。

    Returns:
        合并后的统计 dict（可能为同一对象引用）。
    """
    redis_totals = get_cached_redis_api_totals()
    if not redis_totals or redis_totals.get("request_count", 0) <= 0:
        return local_stats

    result = dict(local_stats)
    req = int(redis_totals["request_count"])
    err = int(redis_totals.get("error_count", 0))
    total_duration = round(float(redis_totals.get("total_duration", 0)), 3)
    slow = int(redis_totals.get("slow_request_count", 0))

    result["request_count"] = req
    result["error_count"] = err
    result["total_duration"] = total_duration
    result["slow_request_count"] = slow
    result["very_slow_request_count"] = int(redis_totals.get("very_slow_request_count", 0))
    if req > 0:
        result["average_duration"] = round(total_duration / req, 3)
        result["error_rate"] = round(err / req, 4)
    return result
