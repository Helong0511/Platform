"""
数据库查询性能监控模块

功能：
- 监控慢查询
- 记录查询执行时间
- 提供查询性能统计

使用方法：
    from app.core.query_monitor import monitor_query
    
    # 在查询前后使用
    async with monitor_query("user_list_query"):
        result = await db.execute(query)
"""
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# 查询性能统计
_query_stats = defaultdict(list)
_slow_query_threshold = 1.0  # 慢查询阈值（秒）


@asynccontextmanager
async def monitor_query(query_name: str, threshold: Optional[float] = None):
    """
    监控数据库查询性能
    
    Args:
        query_name: 查询名称（用于标识）
        threshold: 慢查询阈值（秒），默认使用全局阈值
    
    Example:
        async with monitor_query("user_list_query"):
            result = await db.execute(query)
    """
    start_time = time.time()
    threshold = threshold or _slow_query_threshold
    
    try:
        yield
    finally:
        elapsed = time.time() - start_time
        _query_stats[query_name].append(elapsed)
        
        # 记录慢查询
        if elapsed > threshold:
            logger.warning(
                f"慢查询检测: {query_name} 耗时 {elapsed:.3f}秒 (阈值: {threshold}秒)"
            )


def get_query_stats() -> dict:
    """
    获取查询性能统计
    
    Returns:
        查询统计字典，包含每个查询的平均时间、最大时间、调用次数等
    """
    stats = {}
    for query_name, times in _query_stats.items():
        if times:
            stats[query_name] = {
                "count": len(times),
                "avg_time": sum(times) / len(times),
                "max_time": max(times),
                "min_time": min(times),
                "total_time": sum(times)
            }
    return stats


def reset_query_stats():
    """重置查询统计"""
    _query_stats.clear()


def set_slow_query_threshold(threshold: float):
    """设置慢查询阈值（秒）"""
    global _slow_query_threshold
    _slow_query_threshold = threshold

