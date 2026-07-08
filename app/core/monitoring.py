"""
系统监控体系 - 核心模块

功能说明：
- 性能数据采集模块（响应时间、吞吐量、错误率、资源利用率）
- 实时监控仪表盘（多维度数据可视化）
- 异常检测与告警机制（动态阈值告警策略）
- 历史数据分析与趋势预测
- 性能优化闭环流程支持

监控指标体系：
├── API性能指标
│   ├── 响应时间（平均、P50、P90、P95、P99）
│   ├── 吞吐量（QPS）
│   ├── 错误率
│   └── 状态码分布
├── 系统资源指标
│   ├── CPU使用率
│   ├── 内存使用率
│   ├── 磁盘I/O
│   └── 网络流量
├── 业务指标
│   ├── 广告曝光量
│   ├── 点击量
│   ├── 转化率
│   └── 业务成功率

告警机制：
- 动态阈值告警（支持静态阈值和自适应阈值）
- 多级别告警（INFO、WARNING、ERROR、CRITICAL）
- 告警抑制与聚合
- 多种告警渠道（日志、Telegram、邮件）

@module app.core.monitoring
"""
import asyncio
import logging
import os
import psutil
import random
import time
import uuid
from collections import defaultdict
from datetime import datetime as dt, timedelta, timezone
from threading import Lock, RLock
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ====== 告警级别定义 ======
class AlertLevel:
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

# ====== 指标类型定义 ======
class MetricType:
    GAUGE = "gauge"       # 瞬时值指标（如CPU使用率）
    COUNTER = "counter"   # 计数器指标（如请求总数）
    HISTOGRAM = "histogram" # 直方图指标（如响应时间分布）
    TIMER = "timer"       # 计时器指标

# ====== 监控配置 ======
class MonitoringConfig:
    """监控配置类"""
    def __init__(self):
        # 慢请求阈值（秒）
        self.slow_request_threshold = 3.0
        # 非常慢请求阈值（秒）
        self.very_slow_request_threshold = 8.0
        # 错误率告警阈值（0.0-1.0）
        self.error_rate_threshold = 0.1
        # 告警间隔（秒）- 防止告警刷屏
        self.alert_interval = 60
        # 统计窗口大小（秒）
        self.statistics_window = 60
        # 历史数据保留时间（小时）
        self.history_retention_hours = 24
        # 最大慢请求记录数
        self.max_slow_requests = 100
        # 单窗口内保留的耗时样本上限（用于 P99 等，避免内存与排序开销失控）
        self.max_duration_samples = 2000
        # 资源监控间隔（秒）
        self.resource_monitor_interval = 10
        # 是否启用资源监控
        self.enable_resource_monitor = True
        # 路径级统计采样率（0~1），降低中间件锁竞争；全局计数始终记录
        try:
            self.path_stats_sample_rate = float(os.getenv("MONITOR_PATH_SAMPLE_RATE", "1.0"))
        except ValueError:
            self.path_stats_sample_rate = 1.0
        self.path_stats_sample_rate = max(0.0, min(1.0, self.path_stats_sample_rate))

# ====== 单个指标记录 ======
class MetricRecord:
    """单个指标记录"""
    def __init__(self, name: str, value: float, metric_type: str = MetricType.GAUGE, 
                 labels: Optional[Dict[str, str]] = None, timestamp: Optional[dt] = None):
        self.name = name
        self.value = value
        self.metric_type = metric_type
        self.labels = labels or {}
        self.timestamp = timestamp or dt.now(timezone.utc)

# ====== 请求记录 ======
class RequestRecord:
    """单个请求记录"""
    def __init__(self, method: str, path: str, status_code: int, duration: float, 
                 client_ip: str, timestamp: Optional[dt] = None, 
                 extra: Optional[Dict[str, Any]] = None):
        self.method = method
        self.path = path
        self.status_code = status_code
        self.duration = duration
        self.client_ip = client_ip
        self.timestamp = timestamp or dt.now(timezone.utc)
        self.extra = extra or {}

# ====== 百分位数计算 ======
def linear_percentile(sorted_values: List[float], percentile: float) -> float:
    """
    线性插值百分位数（percentile 为 0~1，如 0.99 表示 P99）。

    使用 rank = (n - 1) * p，避免 int(n * p) 在样本较少时偏差过大。
    """
    n = len(sorted_values)
    if n == 0:
        return 0.0
    if n == 1:
        return float(sorted_values[0])

    rank = (n - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, n - 1)
    if lower == upper:
        return float(sorted_values[lower])
    fraction = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


# ====== 性能统计 ======
class PerformanceStatistics:
    """性能统计类"""
    def __init__(self):
        self.request_count = 0
        self.total_duration = 0.0
        self.status_codes: Dict[int, int] = defaultdict(int)
        self.durations: List[float] = []
        self.slow_request_count = 0
        self.very_slow_request_count = 0
        self.error_count = 0
        self.start_time = dt.now(timezone.utc)
    
    @property
    def average_duration(self) -> float:
        """平均响应时间"""
        if self.request_count == 0:
            return 0.0
        return self.total_duration / self.request_count
    
    @property
    def error_rate(self) -> float:
        """错误率"""
        if self.request_count == 0:
            return 0.0
        return self.error_count / self.request_count
    
    @property
    def qps(self) -> float:
        """每秒查询数"""
        elapsed = (dt.now(timezone.utc) - self.start_time).total_seconds()
        if elapsed <= 0:
            return 0.0
        return self.request_count / elapsed
    
    def calculate_percentiles(self) -> Dict[str, float]:
        """计算百分位数"""
        if not self.durations:
            return {'p50': 0.0, 'p90': 0.0, 'p95': 0.0, 'p99': 0.0}

        sorted_durations = sorted(self.durations)
        return {
            'p50': linear_percentile(sorted_durations, 0.50),
            'p90': linear_percentile(sorted_durations, 0.90),
            'p95': linear_percentile(sorted_durations, 0.95),
            'p99': linear_percentile(sorted_durations, 0.99),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        percentiles = self.calculate_percentiles()
        return {
            'request_count': self.request_count,
            'total_duration': round(self.total_duration, 3),
            'average_duration': round(self.average_duration, 3),
            'qps': round(self.qps, 2),
            'status_codes': dict(self.status_codes),
            'slow_request_count': self.slow_request_count,
            'very_slow_request_count': self.very_slow_request_count,
            'error_count': self.error_count,
            'error_rate': round(self.error_rate, 4),
            'percentiles': {k: round(v, 3) for k, v in percentiles.items()},
            'start_time': self.start_time.isoformat()
        }

    def to_history_snapshot(self, max_duration_samples: Optional[int] = None) -> "PerformanceStatistics":
        """
        历史窗口快照：保留聚合计数与截断后的耗时样本。

        耗时样本供 get_overall_api_stats / get_path_stats 跨窗口合并后计算百分位；
        归档时再次截断，避免历史窗口堆积过多样本占用内存。
        """
        snap = PerformanceStatistics()
        snap.request_count = self.request_count
        snap.total_duration = self.total_duration
        snap.status_codes = defaultdict(int, self.status_codes)
        snap.slow_request_count = self.slow_request_count
        snap.very_slow_request_count = self.very_slow_request_count
        snap.error_count = self.error_count
        snap.start_time = self.start_time
        if self.durations:
            if max_duration_samples is not None and max_duration_samples > 0:
                snap.durations = list(self.durations[-max_duration_samples:])
            else:
                snap.durations = list(self.durations)
        return snap

# ====== 系统资源统计 ======
class ResourceStatistics:
    """系统资源统计类"""
    def __init__(self):
        self.timestamps: List[dt] = []
        self.cpu_percentages: List[float] = []
        self.memory_percentages: List[float] = []
        self.disk_usage_percentages: List[float] = []
        self.network_io: List[Dict[str, float]] = []
        self.process_count: List[int] = []
    
    def add_sample(self, cpu_pct: float, memory_pct: float, disk_pct: float, 
                   network_sent: float, network_recv: float, process_count: int):
        """添加资源采样"""
        self.timestamps.append(dt.now(timezone.utc))
        self.cpu_percentages.append(cpu_pct)
        self.memory_percentages.append(memory_pct)
        self.disk_usage_percentages.append(disk_pct)
        self.network_io.append({
            'sent': network_sent,
            'recv': network_recv
        })
        self.process_count.append(process_count)
        
        # 保持最近100个样本
        max_samples = 100
        if len(self.timestamps) > max_samples:
            self.timestamps.pop(0)
            self.cpu_percentages.pop(0)
            self.memory_percentages.pop(0)
            self.disk_usage_percentages.pop(0)
            self.network_io.pop(0)
            self.process_count.pop(0)
    
    def snapshot_series(self) -> Tuple[List[dt], List[float], List[float]]:
        """复制时间轴与 CPU/内存序列，供持锁外安全读取。"""
        return (
            list(self.timestamps),
            list(self.cpu_percentages),
            list(self.memory_percentages),
        )

    @staticmethod
    def _percent_series_summary(values: List[float]) -> Dict[str, float]:
        if not values:
            return {'current': 0.0, 'avg': 0.0, 'max': 0.0, 'min': 0.0}
        return {
            'current': round(values[-1], 2),
            'avg': round(sum(values) / len(values), 2),
            'max': round(max(values), 2),
            'min': round(min(values), 2),
        }

    def get_summary(self) -> Dict[str, Any]:
        """获取资源统计摘要"""
        if not self.timestamps:
            return {
                'cpu': {'current': 0.0, 'avg': 0.0, 'max': 0.0, 'min': 0.0},
                'memory': {'current': 0.0, 'avg': 0.0, 'max': 0.0, 'min': 0.0},
                'disk': {'current': 0.0, 'avg': 0.0, 'max': 0.0, 'min': 0.0},
                'network': {'avg_sent': 0.0, 'avg_recv': 0.0},
                'process_count': {'current': 0, 'avg': 0}
            }

        network_io = self.network_io or []
        process_count = self.process_count or []

        return {
            'cpu': self._percent_series_summary(self.cpu_percentages),
            'memory': self._percent_series_summary(self.memory_percentages),
            'disk': self._percent_series_summary(self.disk_usage_percentages),
            'network': {
                'avg_sent': round(
                    sum(io.get('sent', 0.0) for io in network_io) / len(network_io), 2
                ) if network_io else 0.0,
                'avg_recv': round(
                    sum(io.get('recv', 0.0) for io in network_io) / len(network_io), 2
                ) if network_io else 0.0,
            },
            'process_count': {
                'current': process_count[-1] if process_count else 0,
                'avg': int(sum(process_count) / len(process_count)) if process_count else 0,
            }
        }

# ====== 告警规则 ======
class AlertRule:
    """
    告警规则：将监控指标与阈值、运算符绑定，由 SystemMonitor._check_alerts 周期性评估。

    Attributes:
        name: 规则唯一标识
        metric_name: 指标名（如 api.error_rate、system.cpu_usage）
        operator: 比较运算符（>、<、>=、<=、==、!=）
        threshold: 触发阈值
        level: 告警级别（INFO/WARNING/ERROR/CRITICAL）
        window_seconds: 评估窗口（秒），与统计窗口轮转对齐
    """
    def __init__(self, name: str, metric_name: str, operator: str, threshold: float,
                 level: str = AlertLevel.WARNING, description: str = "",
                 enabled: bool = True, aggregation: str = "avg", window_seconds: int = 60):
        self.name = name
        self.metric_name = metric_name
        self.operator = operator  # >, <, >=, <=, ==
        self.threshold = threshold
        self.level = level
        self.description = description
        self.enabled = enabled
        self.aggregation = aggregation  # avg, max, min, sum, count
        self.window_seconds = window_seconds
    
    def evaluate(self, value: float) -> bool:
        """评估是否触发告警"""
        if not self.enabled:
            return False
        
        operators = {
            '>': lambda a, b: a > b,
            '<': lambda a, b: a < b,
            '>=': lambda a, b: a >= b,
            '<=': lambda a, b: a <= b,
            '==': lambda a, b: a == b,
            '!=': lambda a, b: a != b
        }
        
        op_func = operators.get(self.operator)
        if not op_func:
            return False
        
        return op_func(value, self.threshold)

# ====== 告警记录 ======
class AlertRecord:
    """已触发告警的持久化记录，支持确认（acknowledge）以在仪表盘隐藏未处理项。"""
    def __init__(self, rule_name: str, metric_name: str, value: float, threshold: float,
                 level: str, description: str, timestamp: Optional[dt] = None):
        self.id = f"alert_{uuid.uuid4().hex}"
        self.rule_name = rule_name
        self.metric_name = metric_name
        self.value = value
        self.threshold = threshold
        self.level = level
        self.description = description
        self.timestamp = timestamp or dt.now(timezone.utc)
        self.acknowledged = False
        self.acknowledged_at = None
    
    def acknowledge(self):
        """确认告警（幂等：已确认时保留首次确认时间）"""
        if self.acknowledged:
            return
        self.acknowledged = True
        self.acknowledged_at = dt.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return {
            'id': self.id,
            'rule_name': self.rule_name,
            'metric_name': self.metric_name,
            'value': self.value,
            'threshold': self.threshold,
            'level': self.level,
            'description': self.description,
            'timestamp': self.timestamp.isoformat(),
            'acknowledged': self.acknowledged,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None
        }

def _lookup_resource_sample_at(
    target_ts: dt,
    resource_timestamps: List[dt],
    cpu_percentages: List[float],
    memory_percentages: List[float],
) -> tuple[float, float]:
    """取不晚于 target_ts 的最近资源采样（用于与 API 历史时间轴对齐）。"""
    if not resource_timestamps:
        return 0.0, 0.0
    chosen = None
    for i, ts in enumerate(resource_timestamps):
        if ts <= target_ts:
            chosen = i
        else:
            break
    if chosen is None:
        return 0.0, 0.0
    cpu = cpu_percentages[chosen] if chosen < len(cpu_percentages) else 0.0
    mem = memory_percentages[chosen] if chosen < len(memory_percentages) else 0.0
    return cpu, mem


def _build_resource_series_from_lists(
    cutoff_time: dt,
    resource_timestamps: List[dt],
    cpu_percentages: List[float],
    memory_percentages: List[float],
) -> tuple[List[str], List[float], List[float]]:
    """按资源采样时间构建 timestamps/cpu/memory，三者长度一致。"""
    timestamps: List[str] = []
    cpu_values: List[float] = []
    memory_values: List[float] = []
    for i, ts in enumerate(resource_timestamps):
        if ts < cutoff_time:
            continue
        timestamps.append(ts.isoformat())
        cpu_values.append(cpu_percentages[i] if i < len(cpu_percentages) else 0.0)
        memory_values.append(memory_percentages[i] if i < len(memory_percentages) else 0.0)
    return timestamps, cpu_values, memory_values


def _build_resource_series_in_range(
    cutoff_time: dt,
    resource_stats: ResourceStatistics,
) -> tuple[List[str], List[float], List[float]]:
    """按资源采样时间构建 timestamps/cpu/memory，三者长度一致。"""
    res_ts, res_cpu, res_mem = resource_stats.snapshot_series()
    return _build_resource_series_from_lists(cutoff_time, res_ts, res_cpu, res_mem)


def build_flat_monitoring_metrics(
    api_stats: Optional[Dict[str, Any]] = None,
    resource_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    """将 API / 资源统计字典展平为告警与瓶颈检测用的指标映射（缺字段时安全降级）。"""
    api = api_stats or {}
    resources = resource_stats or {}
    percentiles = api.get('percentiles') or {}

    request_count = int(api.get('request_count') or 0)
    slow_request_count = int(api.get('slow_request_count') or 0)

    cpu = resources.get('cpu') or {}
    memory = resources.get('memory') or {}
    disk = resources.get('disk') or {}

    def _float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    return {
        'api.request_count': float(request_count),
        'api.average_duration': _float(api.get('average_duration')),
        'api.error_rate': _float(api.get('error_rate')),
        'api.slow_request_rate': slow_request_count / max(request_count, 1),
        'api.response_time_p50': _float(percentiles.get('p50')),
        'api.response_time_p90': _float(percentiles.get('p90')),
        'api.response_time_p95': _float(percentiles.get('p95')),
        'api.response_time_p99': _float(percentiles.get('p99')),
        'api.qps': _float(api.get('qps')),
        'system.cpu_usage': _float(cpu.get('current')),
        'system.memory_usage': _float(memory.get('current')),
        'system.disk_usage': _float(disk.get('current')),
    }

# ====== 监控器核心类 ======
class SystemMonitor:
    """
    系统监控器单例：采集 API / 资源指标、轮转统计窗口、评估告警规则。

    并发模型：
    - 请求路径通过 _stats_lock（RLock）保护 current_api_stats / path_stats
    - rotate_window 在锁内归档后于锁外触发 _check_alerts，避免告警检查阻塞写入
    - 单例创建使用类级 _lock 双重检查
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance
    
    def _init(self):
        """初始化监控器状态与默认告警规则。"""
        self.config = MonitoringConfig()
        
        # API 性能：当前分钟窗口 + 按时间戳归档的历史窗口列表
        self.current_api_stats = PerformanceStatistics()
        self.history_api_stats: List[Tuple[dt, PerformanceStatistics]] = []
        
        # 慢请求记录
        self.slow_requests: List[RequestRecord] = []
        
        # 按路径分组：当前窗口 + 历史窗口（与 history_api_stats 同步轮转）
        self.path_stats: Dict[str, PerformanceStatistics] = defaultdict(PerformanceStatistics)
        self.history_path_stats: List[Tuple[dt, Dict[str, PerformanceStatistics]]] = []
        
        # 系统资源统计
        self.resource_stats = ResourceStatistics()
        
        # 自定义指标
        self.custom_metrics: Dict[str, List[MetricRecord]] = defaultdict(list)
        
        # 告警规则
        self.alert_rules: List[AlertRule] = []
        self._init_default_alert_rules()
        
        # 告警记录
        self.alert_records: List[AlertRecord] = []
        self.max_alerts = 1000
        
        # 告警抑制（防止刷屏）
        self.last_alert_times: Dict[str, float] = {}
        
        # 可重入锁：rotate_window 内会触发告警检查并再次读取统计
        self._stats_lock = RLock()
        
        # 资源监控任务状态
        self._resource_monitor_task = None
        self._resource_monitor_running = False
    
    def _init_default_alert_rules(self):
        """初始化默认告警规则"""
        self.alert_rules = [
            # API性能告警
            AlertRule(
                name="slow_request_warning",
                metric_name="api.slow_request_rate",
                operator=">",
                threshold=0.1,
                level=AlertLevel.WARNING,
                description="慢请求率超过10%",
                window_seconds=60
            ),
            AlertRule(
                name="slow_request_critical",
                metric_name="api.slow_request_rate",
                operator=">",
                threshold=0.3,
                level=AlertLevel.CRITICAL,
                description="慢请求率超过30%",
                window_seconds=60
            ),
            AlertRule(
                name="error_rate_warning",
                metric_name="api.error_rate",
                operator=">",
                threshold=0.05,
                level=AlertLevel.WARNING,
                description="错误率超过5%",
                window_seconds=60
            ),
            AlertRule(
                name="error_rate_critical",
                metric_name="api.error_rate",
                operator=">",
                threshold=0.1,
                level=AlertLevel.CRITICAL,
                description="错误率超过10%",
                window_seconds=60
            ),
            AlertRule(
                name="response_time_p99",
                metric_name="api.response_time_p99",
                operator=">",
                threshold=5.0,
                level=AlertLevel.WARNING,
                description="P99响应时间超过5秒",
                window_seconds=60
            ),
            # 系统资源告警
            AlertRule(
                name="cpu_high",
                metric_name="system.cpu_usage",
                operator=">",
                threshold=80.0,
                level=AlertLevel.WARNING,
                description="CPU使用率超过80%",
                window_seconds=30
            ),
            AlertRule(
                name="cpu_critical",
                metric_name="system.cpu_usage",
                operator=">",
                threshold=95.0,
                level=AlertLevel.CRITICAL,
                description="CPU使用率超过95%",
                window_seconds=30
            ),
            AlertRule(
                name="memory_high",
                metric_name="system.memory_usage",
                operator=">",
                threshold=85.0,
                level=AlertLevel.WARNING,
                description="内存使用率超过85%",
                window_seconds=30
            ),
            AlertRule(
                name="memory_critical",
                metric_name="system.memory_usage",
                operator=">",
                threshold=95.0,
                level=AlertLevel.CRITICAL,
                description="内存使用率超过95%",
                window_seconds=30
            ),
            AlertRule(
                name="disk_high",
                metric_name="system.disk_usage",
                operator=">",
                threshold=80.0,
                level=AlertLevel.WARNING,
                description="磁盘使用率超过80%",
                window_seconds=300
            )
        ]
    
    def _append_duration(self, stats: PerformanceStatistics, duration: float) -> None:
        """追加耗时样本并限制列表长度。"""
        stats.durations.append(duration)
        self._trim_duration_samples(stats)

    def _trim_duration_samples(self, stats: PerformanceStatistics) -> None:
        """将耗时样本列表截断到配置上限，防止百分位计算内存失控。"""
        max_samples = self.config.max_duration_samples
        if len(stats.durations) > max_samples:
            stats.durations = stats.durations[-max_samples:]

    def _accumulate_stats(
        self, target: PerformanceStatistics, source: PerformanceStatistics
    ) -> None:
        """将 source 的聚合计数与耗时样本累加到 target（用于跨窗口合并）。"""
        target.request_count += source.request_count
        target.total_duration += source.total_duration
        for code, count in source.status_codes.items():
            target.status_codes[code] += count
        target.slow_request_count += source.slow_request_count
        target.very_slow_request_count += source.very_slow_request_count
        target.error_count += source.error_count
        if source.durations:
            target.durations.extend(source.durations)

    def _merge_all_path_stats_locked(self) -> Dict[str, PerformanceStatistics]:
        """在已持有 _stats_lock 时，合并历史路径窗口与当前路径统计。"""
        merged: Dict[str, PerformanceStatistics] = {}

        def bucket(path_key: str) -> PerformanceStatistics:
            if path_key not in merged:
                merged[path_key] = PerformanceStatistics()
            return merged[path_key]

        for _, path_snapshot in self.history_path_stats:
            for path_key, stats in path_snapshot.items():
                self._accumulate_stats(bucket(path_key), stats)

        for path_key, stats in self.path_stats.items():
            if stats.request_count > 0:
                self._accumulate_stats(bucket(path_key), stats)

        for stats in merged.values():
            self._trim_duration_samples(stats)

        return merged
    
    # ====== API性能监控 ======
    
    def record_request(self, method: str, path: str, status_code: int, duration: float, 
                       client_ip: str = "unknown", extra: Optional[Dict[str, Any]] = None,
                       *, record_path: bool = True) -> None:
        """
        记录单个API请求
        
        Args:
            method: HTTP方法
            path: 请求路径
            status_code: 响应状态码
            duration: 请求耗时（秒）
            client_ip: 客户端IP
            extra: 额外信息
        """
        with self._stats_lock:
            # 更新当前窗口统计
            self.current_api_stats.request_count += 1
            self.current_api_stats.total_duration += duration
            self.current_api_stats.status_codes[status_code] += 1
            self._append_duration(self.current_api_stats, duration)
            
            # 记录慢请求
            if duration >= self.config.slow_request_threshold:
                self.current_api_stats.slow_request_count += 1
                
                if duration >= self.config.very_slow_request_threshold:
                    self.current_api_stats.very_slow_request_count += 1
                
                # 添加到慢请求列表
                record = RequestRecord(method, path, status_code, duration, client_ip, extra=extra)
                self.slow_requests.append(record)
                # 保持列表大小限制
                if len(self.slow_requests) > self.config.max_slow_requests:
                    self.slow_requests.pop(0)
            
            # 记录错误
            if status_code >= 400:
                self.current_api_stats.error_count += 1
            
            # 按路径分组（可采样以降低开销）
            if record_path:
                path_key = f"{method}:{path}"
                path_stat = self.path_stats[path_key]
                path_stat.request_count += 1
                path_stat.total_duration += duration
                path_stat.status_codes[status_code] += 1
                self._append_duration(path_stat, duration)
                if duration >= self.config.slow_request_threshold:
                    path_stat.slow_request_count += 1
                    if duration >= self.config.very_slow_request_threshold:
                        path_stat.very_slow_request_count += 1
                if status_code >= 400:
                    path_stat.error_count += 1

        # 跨 Worker Redis 汇总（异步 fire-and-forget，不阻塞请求路径）
        slow = duration >= self.config.slow_request_threshold
        very_slow = duration >= self.config.very_slow_request_threshold
        try:
            loop = asyncio.get_running_loop()
            from app.core.monitoring_redis import record_api_request_async

            loop.create_task(
                record_api_request_async(
                    status_code=status_code,
                    duration=duration,
                    slow=slow,
                    very_slow=very_slow,
                )
            )
        except RuntimeError:
            # 同步上下文调用 record_request 时无法调度 async 任务；仅保留本进程统计
            logger.debug(
                "跨 Worker 监控 Redis 写入跳过：当前不在 async 事件循环中，"
                "API 计数仅写入本进程；多 Worker 汇总依赖 refresh_api_totals_cache"
            )
    
    # ====== 系统资源监控 ======
    
    def _collect_resource_metrics(self):
        """收集系统资源指标"""
        try:
            # 首次 interval=None 可能为 0，循环采样后会稳定
            cpu_pct = psutil.cpu_percent(interval=None)
            
            # 内存使用率
            memory = psutil.virtual_memory()
            memory_pct = memory.percent
            
            # 磁盘使用率
            disk = psutil.disk_usage('/')
            disk_pct = disk.percent
            
            # 网络IO
            net_io = psutil.net_io_counters()
            network_sent = net_io.bytes_sent / 1024 / 1024  # MB
            network_recv = net_io.bytes_recv / 1024 / 1024  # MB
            
            # 进程数
            process_count = len(psutil.pids())
            
            # 添加到统计（与 get_resource_stats 等同锁，避免线程池写入与 API 读取竞态）
            with self._stats_lock:
                self.resource_stats.add_sample(cpu_pct, memory_pct, disk_pct,
                                              network_sent, network_recv, process_count)
            
            # 更新自定义指标
            self.record_metric("system.cpu_usage", cpu_pct, MetricType.GAUGE)
            self.record_metric("system.memory_usage", memory_pct, MetricType.GAUGE)
            self.record_metric("system.disk_usage", disk_pct, MetricType.GAUGE)
            
        except Exception as e:
            logger.error(f"收集资源指标失败: {e}")
    
    async def _resource_monitor_loop(self):
        """资源监控循环（阻塞 psutil 调用在线程池中执行，避免卡住事件循环）。"""
        samples_since_alert_check = 0
        # 约每 30 秒评估一次告警（resource_monitor_interval 默认 10 秒）
        alert_check_every_samples = max(1, 30 // max(1, self.config.resource_monitor_interval))
        try:
            while self._resource_monitor_running:
                try:
                    await asyncio.to_thread(self._collect_resource_metrics)
                    samples_since_alert_check += 1
                    if samples_since_alert_check >= alert_check_every_samples:
                        samples_since_alert_check = 0
                        self._check_alerts()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"资源监控循环异常: {e}")
                try:
                    await asyncio.sleep(self.config.resource_monitor_interval)
                except asyncio.CancelledError:
                    raise
        except asyncio.CancelledError:
            logger.debug("【系统监控】资源监控循环已取消")
            raise
    
    async def start_resource_monitor(self):
        """启动资源监控（须在异步上下文中调用）。"""
        if not self.config.enable_resource_monitor:
            return

        if self._resource_monitor_running:
            return

        self._resource_monitor_running = True
        self._resource_monitor_task = asyncio.create_task(self._resource_monitor_loop())
        logger.info("【系统监控】资源监控已启动")
    
    async def stop_resource_monitor(self):
        """停止资源监控并等待后台任务结束。"""
        self._resource_monitor_running = False
        task = self._resource_monitor_task
        self._resource_monitor_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("【系统监控】资源监控已停止")
    
    # ====== 自定义指标 ======
    
    def record_metric(self, name: str, value: float, metric_type: str = MetricType.GAUGE,
                      labels: Optional[Dict[str, str]] = None):
        """
        记录自定义指标
        
        Args:
            name: 指标名称
            value: 指标值
            metric_type: 指标类型
            labels: 标签字典
        """
        with self._stats_lock:
            record = MetricRecord(name, value, metric_type, labels)
            self.custom_metrics[name].append(record)
            
            # 保持最近1000条记录
            max_records = 1000
            if len(self.custom_metrics[name]) > max_records:
                self.custom_metrics[name] = self.custom_metrics[name][-max_records:]
    
    def get_metric_history(self, name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取指标历史记录
        
        Args:
            name: 指标名称
            limit: 返回数量限制
        
        Returns:
            指标历史列表
        """
        with self._stats_lock:
            records = self.custom_metrics.get(name, [])[-limit:]
            return [{
                'value': record.value,
                'timestamp': record.timestamp.isoformat(),
                'labels': record.labels
            } for record in records]
    
    # ====== 告警机制 ======
    
    def add_alert_rule(self, rule: AlertRule):
        """添加告警规则"""
        with self._stats_lock:
            self.alert_rules.append(rule)
            logger.info(f"【系统监控】已添加告警规则: {rule.name}")
    
    def remove_alert_rule(self, rule_name: str):
        """移除告警规则"""
        with self._stats_lock:
            self.alert_rules = [r for r in self.alert_rules if r.name != rule_name]
            logger.info(f"【系统监控】已移除告警规则: {rule_name}")
    
    def update_alert_rule(self, rule_name: str, **kwargs):
        """更新告警规则"""
        with self._stats_lock:
            for rule in self.alert_rules:
                if rule.name == rule_name:
                    for key, value in kwargs.items():
                        if hasattr(rule, key):
                            setattr(rule, key, value)
                    logger.info(f"【系统监控】已更新告警规则: {rule_name}")
                    return True
            return False
    
    def toggle_alert_rule(self, rule_name: str) -> bool:
        """切换告警规则的启用/禁用状态"""
        with self._stats_lock:
            for rule in self.alert_rules:
                if rule.name == rule_name:
                    rule.enabled = not rule.enabled
                    logger.info(f"【系统监控】已切换告警规则状态: {rule_name} -> {'启用' if rule.enabled else '禁用'}")
                    return True
            return False

    def get_alert_rules_snapshot(self) -> List["AlertRule"]:
        """返回告警规则列表快照，供无锁迭代或 API 读取。"""
        with self._stats_lock:
            return list(self.alert_rules)

    def get_alert_rule(self, rule_name: str) -> Optional["AlertRule"]:
        """按名称查找告警规则（持锁读取）。"""
        with self._stats_lock:
            for rule in self.alert_rules:
                if rule.name == rule_name:
                    return rule
            return None

    def _check_alerts(self):
        """检查所有告警规则（规则列表在锁内快照，避免与增删改并发迭代）。"""
        now = time.time()

        # 获取当前指标值（内部会短暂持锁读取统计）
        metrics = self._get_current_metrics()

        rules_snapshot = self.get_alert_rules_snapshot()

        for rule in rules_snapshot:
            if not rule.enabled:
                continue

            value = metrics.get(rule.metric_name, 0.0)

            if rule.evaluate(value):
                alert_key = f"{rule.name}:{rule.level}"
                should_trigger = False
                with self._stats_lock:
                    last_alert_time = self.last_alert_times.get(alert_key, 0.0)
                    if now - last_alert_time >= self.config.alert_interval:
                        self.last_alert_times[alert_key] = now
                        should_trigger = True
                if should_trigger:
                    self._trigger_alert(rule, value)
    
    def _get_current_metrics(self) -> Dict[str, float]:
        """获取当前所有指标值"""
        return build_flat_monitoring_metrics(
            self.get_overall_api_stats(),
            self.get_resource_stats(),
        )
    
    def _trigger_alert(self, rule: AlertRule, value: float):
        """触发告警"""
        alert = AlertRecord(
            rule_name=rule.name,
            metric_name=rule.metric_name,
            value=value,
            threshold=rule.threshold,
            level=rule.level,
            description=rule.description
        )
        
        # 添加到告警记录
        with self._stats_lock:
            self.alert_records.append(alert)
            if len(self.alert_records) > self.max_alerts:
                self.alert_records.pop(0)
        
        # 记录日志告警
        log_level = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.ERROR: logging.ERROR,
            AlertLevel.CRITICAL: logging.CRITICAL
        }.get(rule.level, logging.WARNING)
        
        logger.log(log_level, f"【监控告警】[{rule.level}] {rule.name}: {rule.description} (当前值: {value}, 阈值: {rule.threshold})")
    
    def _sorted_alert_records(
        self,
        level: Optional[str] = None,
        acknowledged: Optional[bool] = None,
    ) -> List[AlertRecord]:
        """与 get_alerts 相同的过滤与按时间降序排序（返回 AlertRecord 对象）。"""
        alerts = self.alert_records.copy()
        if level:
            alerts = [a for a in alerts if a.level == level]
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
        alerts.sort(key=lambda x: x.timestamp, reverse=True)
        return alerts
    
    def get_alerts(self, level: Optional[str] = None, acknowledged: Optional[bool] = None, 
                   limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取告警记录
        
        Args:
            level: 告警级别过滤
            acknowledged: 是否已确认过滤
            limit: 返回数量限制
        
        Returns:
            告警记录列表
        """
        with self._stats_lock:
            alerts = self._sorted_alert_records(level, acknowledged)
            return [a.to_dict() for a in alerts[:limit]]
    
    def acknowledge_alert(
        self,
        index: int,
        level: Optional[str] = None,
        acknowledged: Optional[bool] = None,
    ) -> bool:
        """
        确认告警（按索引）
        
        Args:
            index: 告警在 get_alerts 同序列表中的索引（过滤后、按时间降序）
            level: 与 get_alerts 一致的级别过滤（可选）
            acknowledged: 与 get_alerts 一致的确认状态过滤（可选）
        
        Returns:
            是否成功确认
        """
        with self._stats_lock:
            alerts = self._sorted_alert_records(level, acknowledged)
            if 0 <= index < len(alerts):
                alerts[index].acknowledge()
                return True
            return False
    
    def acknowledge_alert_by_id(self, alert_id: str) -> bool:
        """
        确认告警（按ID）
        
        Args:
            alert_id: 告警ID
        
        Returns:
            是否成功确认
        """
        with self._stats_lock:
            for alert in self.alert_records:
                if alert.id == alert_id:
                    alert.acknowledge()
                    return True
            return False
    
    def acknowledge_all_alerts(self) -> int:
        """
        确认所有告警
        
        Returns:
            确认的告警数量
        """
        with self._stats_lock:
            count = 0
            for alert in self.alert_records:
                if not alert.acknowledged:
                    alert.acknowledge()
                    count += 1
            return count
    
    # ====== 统计窗口轮转 ======
    
    def rotate_window(self) -> None:
        """
        轮转统计窗口（默认每分钟调用一次）。

        将当前 API 与路径统计归档到 history_*，再重置当前窗口；
        归档快照保留截断后的 durations，供跨窗口百分位合并。
        """
        with self._stats_lock:
            now = dt.now(timezone.utc)
            max_history_windows = int(self.config.history_retention_hours * 60)
            max_samples = self.config.max_duration_samples

            if self.current_api_stats.request_count > 0:
                self.history_api_stats.append(
                    (now, self.current_api_stats.to_history_snapshot(max_samples))
                )

            path_snapshot = {
                path_key: stats.to_history_snapshot(max_samples)
                for path_key, stats in self.path_stats.items()
                if stats.request_count > 0
            }
            if path_snapshot:
                self.history_path_stats.append((now, path_snapshot))

            while len(self.history_api_stats) > max_history_windows:
                self.history_api_stats.pop(0)
            while len(self.history_path_stats) > max_history_windows:
                self.history_path_stats.pop(0)

            self.current_api_stats = PerformanceStatistics()
            self.path_stats = defaultdict(PerformanceStatistics)

        # 告警检查放在锁外，避免长时间占锁阻塞 record_request / metrics 查询
        self._check_alerts()
    
    # ====== 数据查询 ======
    
    def get_overall_api_stats(self) -> Dict[str, Any]:
        """获取总体 API 性能统计：历史与当前窗口聚合，百分位基于合并后的耗时样本。"""
        with self._stats_lock:
            merged = PerformanceStatistics()
            if self.history_api_stats:
                merged.start_time = self.history_api_stats[0][1].start_time
            else:
                merged.start_time = self.current_api_stats.start_time

            for _, stats in self.history_api_stats:
                self._accumulate_stats(merged, stats)
            self._accumulate_stats(merged, self.current_api_stats)
            self._trim_duration_samples(merged)

            from app.core.monitoring_redis import apply_redis_api_totals
            return apply_redis_api_totals(merged.to_dict())
    
    def get_path_stats(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取按路径分组的统计（合并已归档历史窗口与当前窗口）。"""
        with self._stats_lock:
            path_results = []
            merged_paths = self._merge_all_path_stats_locked()
            for path_key, stats in merged_paths.items():
                method, path = path_key.split(":", 1)
                path_result = stats.to_dict()
                path_result.update({
                    'method': method,
                    'path': path
                })
                path_results.append(path_result)
            
            path_results.sort(key=lambda x: x['request_count'], reverse=True)
            return path_results[:limit]
    
    def get_slow_requests(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取慢请求列表"""
        with self._stats_lock:
            sorted_requests = sorted(self.slow_requests, key=lambda r: r.duration, reverse=True)
            return [{
                'method': r.method,
                'path': r.path,
                'status_code': r.status_code,
                'duration': round(r.duration, 3),
                'client_ip': r.client_ip,
                'timestamp': r.timestamp.isoformat(),
                'extra': r.extra
            } for r in sorted_requests[:limit]]
    
    def get_resource_stats(self) -> Dict[str, Any]:
        """获取系统资源统计（持锁读取，与后台采样线程安全）。"""
        with self._stats_lock:
            return self.resource_stats.get_summary()
    
    def get_realtime_metrics(self) -> Dict[str, Any]:
        """获取实时监控指标"""
        return {
            'api': self.get_overall_api_stats(),
            'paths': self.get_path_stats(),
            'slow_requests': self.get_slow_requests(),
            'resources': self.get_resource_stats(),
            'alerts': self.get_alerts(limit=10),
            'timestamp': dt.now(timezone.utc).isoformat()
        }
    
    # ====== 趋势分析 ======
    
    def _snapshot_trend_inputs_locked(
        self, hours: int
    ) -> Tuple[dt, List[dt], List[float], List[float], List[Tuple[Any, ...]]]:
        """在 _stats_lock 内采集趋势数据快照，供 get_trend_data 锁外安全使用。"""
        cutoff_time = dt.now(timezone.utc) - timedelta(hours=hours)
        relevant_history = [
            (ts, stats) for ts, stats in self.history_api_stats
            if ts >= cutoff_time
        ]
        relevant_history.sort(key=lambda x: x[0])
        res_ts, res_cpu, res_mem = self.resource_stats.snapshot_series()
        api_rows = [
            (
                ts,
                stats.request_count,
                round(stats.average_duration, 3),
                round(stats.error_rate, 4),
                round(stats.qps, 2),
            )
            for ts, stats in relevant_history
        ]
        return cutoff_time, res_ts, res_cpu, res_mem, api_rows

    def get_trend_data(self, hours: int = 24) -> Dict[str, Any]:
        """
        获取趋势数据
        
        Args:
            hours: 时间范围（小时）
        
        Returns:
            趋势数据字典
        """
        with self._stats_lock:
            cutoff_time, res_ts, res_cpu, res_mem, api_rows = (
                self._snapshot_trend_inputs_locked(hours)
            )

        if not api_rows:
            timestamps, cpu_values, memory_values = _build_resource_series_from_lists(
                cutoff_time, res_ts, res_cpu, res_mem
            )
            return {
                'timestamps': timestamps,
                'request_counts': [],
                'avg_durations': [],
                'error_rates': [],
                'qps_values': [],
                'cpu_values': cpu_values,
                'memory_values': memory_values,
            }

        api_timestamps = [row[0] for row in api_rows]
        cpu_values = []
        memory_values = []
        for ts in api_timestamps:
            cpu, mem = _lookup_resource_sample_at(ts, res_ts, res_cpu, res_mem)
            cpu_values.append(cpu)
            memory_values.append(mem)

        return {
            'timestamps': [ts.isoformat() for ts in api_timestamps],
            'request_counts': [row[1] for row in api_rows],
            'avg_durations': [row[2] for row in api_rows],
            'error_rates': [row[3] for row in api_rows],
            'qps_values': [row[4] for row in api_rows],
            'cpu_values': cpu_values,
            'memory_values': memory_values,
        }
    
    def predict_trend(self, steps: int = 60) -> Dict[str, Any]:
        """
        简单趋势预测（基于移动平均）
        
        Args:
            steps: 预测步数
        
        Returns:
            预测数据
        """
        trend_data = self.get_trend_data(hours=6)
        avg_durations = trend_data.get('avg_durations') or []
        timestamps = trend_data.get('timestamps') or []
        request_counts = trend_data.get('request_counts') or []
        error_rates = trend_data.get('error_rates') or []

        # 预测仅基于 API 历史；无足够 API 序列或仅有资源采样时不返回误导性预测
        api_series_aligned = (
            len(avg_durations) >= 2
            and len(timestamps) >= 2
            and len(request_counts) >= 2
            and len(avg_durations) == len(timestamps) == len(request_counts) == len(error_rates)
        )
        if not api_series_aligned:
            return {
                'predicted_timestamps': [],
                'predicted_avg_durations': [],
                'predicted_error_rates': []
            }
        
        # 简单移动平均预测
        def moving_average_predict(values, steps):
            if len(values) < 3:
                return [values[-1]] * steps if values else [0.0] * steps
            
            # 使用最近3个值的平均作为预测
            window_size = min(3, len(values))
            avg = sum(values[-window_size:]) / window_size
            return [avg] * steps
        
        # 生成预测时间戳（锚定最后一条历史时间点）
        last_timestamp = dt.fromisoformat(timestamps[-1])
        predicted_timestamps = [
            (last_timestamp + timedelta(minutes=i+1)).isoformat()
            for i in range(steps)
        ]
        
        return {
            'predicted_timestamps': predicted_timestamps,
            'predicted_avg_durations': moving_average_predict(avg_durations, steps),
            'predicted_error_rates': moving_average_predict(error_rates, steps)
        }
    
    def reset(self) -> None:
        """重置所有统计数据"""
        with self._stats_lock:
            self.current_api_stats = PerformanceStatistics()
            self.history_api_stats = []
            self.history_path_stats = []
            self.slow_requests = []
            self.path_stats = defaultdict(PerformanceStatistics)
            self.resource_stats = ResourceStatistics()
            self.custom_metrics = defaultdict(list)
            self.alert_records = []
            self.last_alert_times = {}
        logger.info("【系统监控】已重置所有统计数据")

# ====== 全局监控实例 ======
system_monitor = SystemMonitor()

# ====== 监控中间件 ======
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

class SystemMonitoringMiddleware(BaseHTTPMiddleware):
    """
    系统监控中间件
    
    记录所有API请求的性能指标，并收集系统资源使用情况
    """
    
    _SKIP_PATH_PREFIXES = (
        "/api/v1/monitoring",
        "/api/v1/optimization",
        "/api/v1/health",
        "/assets/",
        "/favicon.ico",
    )
    _SKIP_PATH_SUFFIXES = (".js", ".css", ".map", ".ico", ".woff", ".woff2", ".png", ".jpg", ".svg")

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.app = app
        self._sample_rate = system_monitor.config.path_stats_sample_rate

    @classmethod
    def _should_skip(cls, path: str) -> bool:
        """监控/静态资源等路径不纳入统计，避免轮询与静态流量放大开销。"""
        if any(path.startswith(prefix) for prefix in cls._SKIP_PATH_PREFIXES):
            return True
        lower = path.lower()
        if any(lower.endswith(suffix) for suffix in cls._SKIP_PATH_SUFFIXES):
            return True
        from app.core.sensitive_path_rules import is_bundle_template_placeholder_path

        return is_bundle_template_placeholder_path(path)

    @classmethod
    def _should_sample_path_stats(cls) -> bool:
        rate = system_monitor.config.path_stats_sample_rate
        if rate >= 1.0:
            return True
        if rate <= 0.0:
            return False
        return random.random() < rate
    
    async def dispatch(self, request: Request, call_next):
        """记录请求性能指标"""
        path = request.url.path
        skip_metrics = self._should_skip(path)

        start_time = time.time()
        
        try:
            response = await call_next(request)
        except Exception:
            if not skip_metrics:
                duration = time.time() - start_time
                system_monitor.record_request(
                    method=request.method,
                    path=path,
                    status_code=500,
                    duration=duration,
                    client_ip="unknown",
                    record_path=self._should_sample_path_stats(),
                )
            raise
        
        duration = time.time() - start_time

        if not skip_metrics:
            system_monitor.record_request(
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration=duration,
                client_ip="unknown",
                record_path=self._should_sample_path_stats(),
            )
        
        response.headers["X-Process-Time"] = f"{duration:.4f}"
        
        return response

# ====== 监控路由 ======
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.security import require_admin


def _normalize_alert_operator(operator: str) -> str:
    """前端 gt/lt/ge/le 与后端 >/</>=/<= 互转。"""
    mapping = {
        "gt": ">",
        "lt": "<",
        "ge": ">=",
        "le": "<=",
        "eq": "==",
        "ne": "!=",
    }
    op = (operator or "").strip()
    return mapping.get(op.lower(), op)


def _operator_to_frontend(operator: str) -> str:
    """后端运算符转前端表单值（供列表展示）。"""
    reverse = {
        ">": "gt",
        "<": "lt",
        ">=": "ge",
        "<=": "le",
        "==": "eq",
        "!=": "ne",
    }
    return reverse.get(operator, operator)


def _alert_rule_to_api_dict(rule: AlertRule) -> Dict[str, Any]:
    """告警规则 API 响应（兼容前端 id / rule_name 字段）。"""
    return {
        "id": rule.name,
        "rule_name": rule.name,
        "name": rule.name,
        "metric_name": rule.metric_name,
        "operator": _operator_to_frontend(rule.operator),
        "threshold": rule.threshold,
        "level": rule.level,
        "description": rule.description,
        "enabled": rule.enabled,
        "aggregation": rule.aggregation,
        "window_seconds": rule.window_seconds,
    }


class AlertRuleCreateBody(BaseModel):
    """前端添加告警规则请求体。"""
    rule_name: str = Field(..., description="规则名称")
    metric_name: str
    operator: str
    threshold: float
    level: str = AlertLevel.WARNING
    description: str = ""
    enabled: bool = True
    aggregation: str = "avg"
    window_seconds: int = 60


monitoring_router = APIRouter(tags=["系统监控"], dependencies=[Depends(require_admin)])

@monitoring_router.get("/metrics", summary="获取实时监控指标")
async def get_metrics():
    """
    获取实时系统监控指标，包括：
    - API性能统计
    - 各路径性能统计
    - 慢请求列表
    - 系统资源使用情况
    - 最近告警
    """
    return system_monitor.get_realtime_metrics()

@monitoring_router.get("/metrics/api", summary="获取API性能统计")
async def get_api_metrics():
    """获取API性能统计数据"""
    return system_monitor.get_overall_api_stats()

@monitoring_router.get("/metrics/paths", summary="获取路径性能统计")
async def get_path_metrics(limit: int = Query(10, ge=1, le=100)):
    """
    获取按路径分组的性能统计
    
    Args:
        limit: 返回的路径数量限制（默认10）
    """
    return system_monitor.get_path_stats(limit)

@monitoring_router.get("/metrics/slow-requests", summary="获取慢请求列表")
async def get_slow_requests(limit: int = Query(20, ge=1, le=100)):
    """
    获取慢请求列表
    
    Args:
        limit: 返回的慢请求数量限制（默认20）
    """
    return system_monitor.get_slow_requests(limit)

@monitoring_router.get("/metrics/resources", summary="获取系统资源统计")
async def get_resource_metrics():
    """获取系统资源使用情况（CPU、内存、磁盘、网络）"""
    return system_monitor.get_resource_stats()

@monitoring_router.get("/metrics/trends", summary="获取趋势数据")
async def get_trend_data(hours: int = Query(24, ge=1, le=168)):
    """
    获取历史趋势数据
    
    Args:
        hours: 时间范围（小时），默认24小时，最大168小时（7天）
    """
    return system_monitor.get_trend_data(hours)

@monitoring_router.get("/metrics/predict", summary="获取趋势预测")
async def get_predict_data(steps: int = Query(60, ge=1, le=1440)):
    """
    获取趋势预测数据
    
    Args:
        steps: 预测步数（分钟），默认60分钟，最大1440分钟（24小时）
    """
    return system_monitor.predict_trend(steps)


def build_trend_summary(trend_data: Dict[str, Any]) -> Dict[str, Any]:
    """根据 get_trend_data 返回值生成趋势统计摘要。"""
    avg_durations = trend_data.get('avg_durations', [])
    qps_values = trend_data.get('qps_values', [])
    request_counts = trend_data.get('request_counts', [])
    error_rates = trend_data.get('error_rates', [])
    cpu_values = trend_data.get('cpu_values', [])
    memory_values = trend_data.get('memory_values', [])

    return {
        'avg_duration': sum(avg_durations) / len(avg_durations) if avg_durations else 0,
        'peak_qps': max(qps_values) if qps_values else 0,
        'total_requests': sum(request_counts) if request_counts else 0,
        'avg_error_rate': sum(error_rates) / len(error_rates) if error_rates else 0,
        'max_cpu': max(cpu_values) if cpu_values else 0,
        'max_memory': max(memory_values) if memory_values else 0,
    }

@monitoring_router.get("/metrics/trends/summary", summary="获取趋势统计摘要")
async def get_trend_summary(hours: int = Query(24, ge=1, le=168)):
    """
    获取趋势统计摘要
    
    Args:
        hours: 时间范围（小时），默认24小时，最大168小时（7天）
    """
    trend_data = system_monitor.get_trend_data(hours)
    return build_trend_summary(trend_data)

@monitoring_router.get("/metrics/custom/{name}", summary="获取自定义指标")
async def get_custom_metric(name: str, limit: int = Query(100, ge=1, le=1000)):
    """
    获取自定义指标历史数据
    
    Args:
        name: 指标名称
        limit: 返回数量限制
    """
    return system_monitor.get_metric_history(name, limit)

# ====== 告警管理路由 ======

@monitoring_router.get("/alerts", summary="获取告警列表")
async def get_alerts(
    level: Optional[str] = Query(None, enum=[AlertLevel.INFO, AlertLevel.WARNING, AlertLevel.ERROR, AlertLevel.CRITICAL]),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500)
):
    """
    获取告警记录列表
    
    Args:
        level: 告警级别过滤
        acknowledged: 是否已确认过滤
        limit: 返回数量限制
    """
    return system_monitor.get_alerts(level, acknowledged, limit)

@monitoring_router.put("/alerts/{alert_ref}/acknowledge", summary="确认告警")
async def acknowledge_alert_endpoint(
    alert_ref: str,
    level: Optional[str] = Query(None, enum=[AlertLevel.INFO, AlertLevel.WARNING, AlertLevel.ERROR, AlertLevel.CRITICAL]),
    acknowledged: Optional[bool] = Query(None),
):
    """
    确认告警：alert_ref 为告警 ID（如 alert_xxx）或列表索引（非负整数）。

    与前端 PUT /alerts/{id}/acknowledge 一致；按索引确认时可选 level、acknowledged 过滤参数。
    """
    if system_monitor.acknowledge_alert_by_id(alert_ref):
        return {"message": "告警已确认"}
    if alert_ref.isdigit():
        success = system_monitor.acknowledge_alert(
            int(alert_ref), level=level, acknowledged=acknowledged
        )
        if success:
            return {"message": "告警已确认"}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="告警不存在")

@monitoring_router.put("/alerts/acknowledge-all", summary="确认所有告警")
async def acknowledge_all_alerts():
    """确认所有告警"""
    count = system_monitor.acknowledge_all_alerts()
    return {"message": f"已确认 {count} 条告警", "count": count}

@monitoring_router.get("/alerts/rules", summary="获取告警规则列表")
async def get_alert_rules():
    """获取所有告警规则"""
    return [_alert_rule_to_api_dict(rule) for rule in system_monitor.get_alert_rules_snapshot()]

@monitoring_router.post("/alerts/rules", summary="添加告警规则")
async def add_alert_rule(body: AlertRuleCreateBody):
    """
    添加新的告警规则（接受 JSON 请求体，字段与前端 AlertManagement 一致）
    """
    operator = _normalize_alert_operator(body.operator)
    rule = AlertRule(
        body.rule_name,
        body.metric_name,
        operator,
        body.threshold,
        body.level,
        body.description,
        body.enabled,
        body.aggregation,
        body.window_seconds,
    )
    system_monitor.add_alert_rule(rule)
    return {"message": f"告警规则 '{body.rule_name}' 已添加", "rule": _alert_rule_to_api_dict(rule)}

@monitoring_router.put("/alerts/rules/{name}", summary="更新告警规则")
async def update_alert_rule(
    name: str,
    metric_name: Optional[str] = None,
    operator: Optional[str] = None,
    threshold: Optional[float] = None,
    level: Optional[str] = None,
    description: Optional[str] = None,
    enabled: Optional[bool] = None,
    aggregation: Optional[str] = None,
    window_seconds: Optional[int] = None
):
    """
    更新告警规则
    
    Args:
        name: 规则名称
        metric_name: 监控指标名称（可选）
        operator: 比较运算符（可选）
        threshold: 阈值（可选）
        level: 告警级别（可选）
        description: 规则描述（可选）
        enabled: 是否启用（可选）
        aggregation: 聚合方式（可选）
        window_seconds: 时间窗口（秒）（可选）
    """
    kwargs = {}
    if metric_name is not None:
        kwargs['metric_name'] = metric_name
    if operator is not None:
        kwargs['operator'] = _normalize_alert_operator(operator)
    if threshold is not None:
        kwargs['threshold'] = threshold
    if level is not None:
        kwargs['level'] = level
    if description is not None:
        kwargs['description'] = description
    if enabled is not None:
        kwargs['enabled'] = enabled
    if aggregation is not None:
        kwargs['aggregation'] = aggregation
    if window_seconds is not None:
        kwargs['window_seconds'] = window_seconds
    
    success = system_monitor.update_alert_rule(name, **kwargs)
    if success:
        return {"message": f"告警规则 '{name}' 已更新"}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="告警规则不存在")

@monitoring_router.put("/alerts/rules/{name}/toggle", summary="切换告警规则状态")
async def toggle_alert_rule(name: str):
    """
    切换告警规则的启用/禁用状态
    
    Args:
        name: 规则名称（前端 id 与 rule_name 同值）
    """
    success = system_monitor.toggle_alert_rule(name)
    if success:
        rule = system_monitor.get_alert_rule(name)
        return {
            "message": f"告警规则 '{name}' 状态已切换",
            "rule": _alert_rule_to_api_dict(rule) if rule else None,
        }
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="告警规则不存在")

@monitoring_router.delete("/alerts/rules/{name}", summary="删除告警规则")
async def delete_alert_rule(name: str):
    """
    删除告警规则
    
    Args:
        name: 规则名称
    """
    system_monitor.remove_alert_rule(name)
    return {"message": f"告警规则 '{name}' 已删除"}

# ====== 管理路由 ======

@monitoring_router.post("/reset", summary="重置监控数据")
async def reset_monitoring():
    """重置所有监控统计数据"""
    system_monitor.reset()
    return {"message": "监控数据已重置"}

@monitoring_router.post("/start-resource-monitor", summary="启动资源监控")
async def start_resource_monitor():
    """启动系统资源监控"""
    await system_monitor.start_resource_monitor()
    return {"message": "资源监控已启动"}

@monitoring_router.post("/stop-resource-monitor", summary="停止资源监控")
async def stop_resource_monitor():
    """停止系统资源监控"""
    await system_monitor.stop_resource_monitor()
    return {"message": "资源监控已停止"}

# ====== 定期任务 ======

async def start_monitoring_tasks():
    """
    启动监控定期任务
    
    - 每分钟轮转统计窗口
    - 启动资源监控
    """
    # 预热 CPU 采样，后续 interval=None 才能返回有效值
    try:
        psutil.cpu_percent(interval=None)
    except Exception:
        pass

    await system_monitor.start_resource_monitor()

    from app.core.monitoring_redis import refresh_api_totals_cache

    await refresh_api_totals_cache(system_monitor.config.history_retention_hours)

    # 启动后立即评估一次，避免首分钟内页面统计始终为 0
    system_monitor._check_alerts()

    # 启动统计窗口轮转
    try:
        while True:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                logger.debug("【系统监控】统计窗口轮转任务已取消")
                raise
            system_monitor.rotate_window()
            await refresh_api_totals_cache(system_monitor.config.history_retention_hours)
            logger.debug("【系统监控】统计窗口已轮转")
    except asyncio.CancelledError:
        logger.debug("【系统监控】定期任务已停止")
        raise