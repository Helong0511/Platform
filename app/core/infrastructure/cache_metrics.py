"""
缓存监控指标

提供缓存命中率、错误率等监控指标
"""
import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass, field

from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class CacheMetrics:
    """缓存指标"""
    hits: int = 0
    misses: int = 0
    errors: int = 0
    total_time_ms: float = 0.0
    
    @property
    def total_requests(self) -> int:
        """缓存请求总数（命中 + 未命中，不含错误）。"""
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """命中率，范围 0.0–1.0；无请求时返回 0。"""
        total = self.total_requests
        return self.hits / total if total > 0 else 0.0

    @property
    def error_rate(self) -> float:
        """错误率（errors / 总操作次数），范围 0.0–1.0。"""
        total = self.total_requests + self.errors
        return self.errors / total if total > 0 else 0.0

    @property
    def avg_response_time_ms(self) -> float:
        """平均缓存操作耗时（毫秒），仅统计命中与未命中。"""
        return self.total_time_ms / self.total_requests if self.total_requests > 0 else 0.0

    def to_dict(self) -> Dict:
        """导出为可序列化字典，命中率/错误率为百分比（保留两位小数）。"""
        return {
            'hits': self.hits,
            'misses': self.misses,
            'errors': self.errors,
            'total_requests': self.total_requests,
            'hit_rate': round(self.hit_rate * 100, 2),  # 百分比
            'error_rate': round(self.error_rate * 100, 2),  # 百分比
            'avg_response_time_ms': round(self.avg_response_time_ms, 2),
        }


class CacheMetricsCollector:
    """缓存指标收集器"""
    
    _instance: Optional['CacheMetricsCollector'] = None
    _metrics: Dict[str, CacheMetrics] = field(default_factory=dict)
    
    def __new__(cls):
        """单例收集器：进程内共享各 key_prefix 的命中/未命中计数。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._metrics = {}
        return cls._instance
    
    def get_metrics(self, key_prefix: str = 'global') -> CacheMetrics:
        """
        获取指标
        
        Args:
            key_prefix: 指标前缀（用于分类统计）
        
        Returns:
            CacheMetrics: 指标对象
        """
        if key_prefix not in self._metrics:
            self._metrics[key_prefix] = CacheMetrics()
        return self._metrics[key_prefix]
    
    def record_hit(self, key_prefix: str = 'global', response_time_ms: float = 0.0):
        """记录命中"""
        metrics = self.get_metrics(key_prefix)
        metrics.hits += 1
        metrics.total_time_ms += response_time_ms
    
    def record_miss(self, key_prefix: str = 'global', response_time_ms: float = 0.0):
        """记录未命中"""
        metrics = self.get_metrics(key_prefix)
        metrics.misses += 1
        metrics.total_time_ms += response_time_ms
    
    def record_error(self, key_prefix: str = 'global'):
        """记录错误"""
        metrics = self.get_metrics(key_prefix)
        metrics.errors += 1
    
    def get_all_metrics(self) -> Dict[str, Dict]:
        """获取所有指标"""
        return {
            key: metrics.to_dict()
            for key, metrics in self._metrics.items()
        }
    
    def reset(self):
        """重置所有指标"""
        self._metrics.clear()


# 全局指标收集器实例
_metrics_collector = CacheMetricsCollector()


def get_metrics_collector() -> CacheMetricsCollector:
    """获取指标收集器"""
    return _metrics_collector


async def report_metrics_to_redis():
    """
    上报指标到 Redis（用于集中监控）
    
    建议：通过定时任务每分钟执行一次
    """
    redis = await get_redis_client()
    if not redis:
        return
    
    try:
        metrics = get_metrics_collector().get_all_metrics()
        timestamp = int(time.time())
        
        for key_prefix, data in metrics.items():
            redis_key = f"cache:metrics:{key_prefix}:{timestamp}"
            await redis.setex(
                redis_key,
                3600,  # 1 小时后过期
                str(data)
            )
        
        logger.debug(f"缓存指标已上报到 Redis: {list(metrics.keys())}")
    
    except Exception as e:
        logger.warning(f"上报缓存指标失败：{e}")


async def get_cache_health_status() -> Dict:
    """
    获取缓存健康状态
    
    Returns:
        dict: 健康状态
    """
    metrics = get_metrics_collector().get_metrics('global')
    
    # 健康度评估
    health_score = 100
    
    # 命中率低于 50% 扣分
    if metrics.hit_rate < 0.5:
        health_score -= 20
    elif metrics.hit_rate < 0.7:
        health_score -= 10
    
    # 错误率高于 5% 扣分
    if metrics.error_rate > 0.05:
        health_score -= 30
    elif metrics.error_rate > 0.02:
        health_score -= 10
    
    # 响应时间高于 100ms 扣分
    if metrics.avg_response_time_ms > 100:
        health_score -= 20
    elif metrics.avg_response_time_ms > 50:
        health_score -= 10
    
    # 健康等级
    if health_score >= 90:
        health_level = 'excellent'
    elif health_score >= 70:
        health_level = 'good'
    elif health_score >= 50:
        health_level = 'fair'
    else:
        health_level = 'poor'
    
    return {
        'score': health_score,
        'level': health_level,
        'metrics': metrics.to_dict(),
        'timestamp': int(time.time()),
    }
