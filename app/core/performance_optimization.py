"""
性能优化闭环流程模块

功能说明：
- 基于监控数据识别性能瓶颈
- 制定优化方案
- 实施改进措施
- 通过监控体系验证优化效果
- 形成持续迭代的性能优化机制

优化闭环流程：
┌─────────────────┐
│  性能数据采集   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  瓶颈识别分析   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  制定优化方案   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  实施优化措施   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  验证优化效果   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   持续迭代改进  │
└─────────────────┘

优化方案状态：
- PENDING: 待审核
- APPROVED: 已批准
- IMPLEMENTING: 实施中
- COMPLETED: 已完成
- VERIFIED: 已验证
- REJECTED: 已拒绝

@module app.core.performance_optimization
"""
import asyncio
import datetime
import logging
import uuid
from datetime import datetime as dt, timezone
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional

from app.core.monitoring import build_flat_monitoring_metrics, system_monitor

logger = logging.getLogger(__name__)


# ====== 优化方案状态 ======
class OptimizationStatus(Enum):
    PENDING = "PENDING"      # 待审核
    APPROVED = "APPROVED"    # 已批准
    IMPLEMENTING = "IMPLEMENTING"  # 实施中
    COMPLETED = "COMPLETED"  # 已完成
    VERIFIED = "VERIFIED"    # 已验证
    REJECTED = "REJECTED"    # 已拒绝


# ====== 瓶颈类型 ======
class BottleneckType(Enum):
    API_RESPONSE_TIME = "API_RESPONSE_TIME"  # API响应时间过长
    HIGH_ERROR_RATE = "HIGH_ERROR_RATE"      # 错误率过高
    HIGH_CPU_USAGE = "HIGH_CPU_USAGE"        # CPU使用率过高
    HIGH_MEMORY_USAGE = "HIGH_MEMORY_USAGE"  # 内存使用率过高
    DATABASE_QUERY = "DATABASE_QUERY"        # 数据库查询慢
    NETWORK_LATENCY = "NETWORK_LATENCY"      # 网络延迟高
    THROUGHPUT = "THROUGHPUT"                # 吞吐量不足
    MEMORY_LEAK = "MEMORY_LEAK"              # 内存泄漏


# ====== 优化方案优先级 ======
class OptimizationPriority(Enum):
    CRITICAL = "CRITICAL"    # 紧急
    HIGH = "HIGH"            # 高
    MEDIUM = "MEDIUM"        # 中
    LOW = "LOW"              # 低


# ====== 瓶颈记录 ======
class BottleneckRecord:
    """瓶颈记录类"""
    def __init__(self, bottleneck_type: BottleneckType, metric_name: str, 
                 current_value: float, threshold: float, description: str,
                 timestamp: Optional[dt] = None):
        self.bottleneck_type = bottleneck_type
        self.metric_name = metric_name
        self.current_value = current_value
        self.threshold = threshold
        self.description = description
        self.timestamp = timestamp or dt.now(timezone.utc)
        self.optimization_plan_id = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'bottleneck_type': self.bottleneck_type.value,
            'metric_name': self.metric_name,
            'current_value': self.current_value,
            'threshold': self.threshold,
            'description': self.description,
            'timestamp': self.timestamp.isoformat(),
            'optimization_plan_id': self.optimization_plan_id
        }


# ====== 优化方案 ======
class OptimizationPlan:
    """优化方案类"""
    def __init__(self, title: str, description: str, bottleneck_type: BottleneckType,
                 priority: OptimizationPriority, estimated_effort: int,
                 expected_improvement: float, owner: str = ""):
        self.id = f"plan_{uuid.uuid4().hex}"
        self.title = title
        self.description = description
        self.bottleneck_type = bottleneck_type
        self.priority = priority
        self.estimated_effort = estimated_effort  # 预估工时（小时）
        self.expected_improvement = expected_improvement  # 预期改进百分比
        self.owner = owner
        self.status = OptimizationStatus.PENDING
        self.created_at = dt.now(timezone.utc)
        self.updated_at = dt.now(timezone.utc)
        self.approved_at = None
        self.completed_at = None
        self.verified_at = None
        self.bottlenecks: List[BottleneckRecord] = []
        self.metrics_before: Dict[str, Any] = {}
        self.metrics_after: Dict[str, Any] = {}
        self.actual_improvement = 0.0
    
    def approve(self):
        """批准优化方案（仅待审核状态可批准）"""
        if self.status != OptimizationStatus.PENDING:
            raise ValueError("只能批准待审核状态的方案")
        self.status = OptimizationStatus.APPROVED
        self.approved_at = dt.now(timezone.utc)
        self.updated_at = dt.now(timezone.utc)
        logger.info(f"【性能优化】优化方案已批准: {self.title}")
    
    def start_implementing(self):
        """开始实施（仅从已批准状态转入实施中）"""
        if self.status != OptimizationStatus.APPROVED:
            raise ValueError("只能从已批准状态开始实施")
        self.status = OptimizationStatus.IMPLEMENTING
        self.updated_at = dt.now(timezone.utc)
        # 记录优化前的指标数据
        self.metrics_before = self._capture_current_metrics()
        logger.info(f"【性能优化】开始实施优化方案: {self.title}")
    
    def complete(self):
        """完成实施"""
        if self.status != OptimizationStatus.IMPLEMENTING:
            raise ValueError("只能在实施中完成")
        self.status = OptimizationStatus.COMPLETED
        self.completed_at = dt.now(timezone.utc)
        self.updated_at = dt.now(timezone.utc)
        logger.info(f"【性能优化】优化方案已完成: {self.title}")
    
    def verify(self):
        """验证优化效果"""
        if self.status != OptimizationStatus.COMPLETED:
            raise ValueError("只能在完成后验证")
        # 记录优化后的指标数据
        self.metrics_after = self._capture_current_metrics()
        # 计算实际改进率
        self.actual_improvement = self._calculate_improvement()
        self.status = OptimizationStatus.VERIFIED
        self.verified_at = dt.now(timezone.utc)
        self.updated_at = dt.now(timezone.utc)
        
        logger.info(f"【性能优化】优化方案验证完成: {self.title}, 实际改进率: {self.actual_improvement:.2%}")
    
    def reject(self, reason: str = ""):
        """拒绝优化方案（仅待审核状态可拒绝）"""
        if self.status != OptimizationStatus.PENDING:
            raise ValueError("只能拒绝待审核状态的方案")
        self.status = OptimizationStatus.REJECTED
        self.updated_at = dt.now(timezone.utc)
        logger.info(f"【性能优化】优化方案已拒绝: {self.title}, 原因: {reason}")
    
    def add_bottleneck(self, bottleneck: BottleneckRecord):
        """关联瓶颈记录"""
        bottleneck.optimization_plan_id = self.id
        self.bottlenecks.append(bottleneck)
    
    def _capture_current_metrics(self) -> Dict[str, Any]:
        """捕获当前指标数据"""
        return {
            'api': system_monitor.get_overall_api_stats(),
            'resources': system_monitor.get_resource_stats(),
            'timestamp': dt.now(timezone.utc).isoformat()
        }
    
    def _calculate_improvement(self) -> float:
        """计算实际改进率（基于 API 平均响应时间）"""
        if not self.metrics_before or not self.metrics_after:
            return 0.0

        before = self.metrics_before.get('api') or {}
        after = self.metrics_after.get('api') or {}

        # 缺少有效采样时不计算改进率，避免空指标被默认 before=1.0 / after=0.0 误判为 100% 提升
        if before.get('request_count', 0) <= 0 or after.get('request_count', 0) <= 0:
            return 0.0

        if 'average_duration' not in before or 'average_duration' not in after:
            return 0.0

        before_avg_duration = before['average_duration']
        after_avg_duration = after['average_duration']

        if not isinstance(before_avg_duration, (int, float)) or not isinstance(after_avg_duration, (int, float)):
            return 0.0

        if before_avg_duration <= 0:
            return 0.0

        if after_avg_duration <= 0:
            return 0.0

        improvement = (before_avg_duration - after_avg_duration) / before_avg_duration
        # 限制在 [-100%, +100%]，避免异常指标导致 UI 出现离谱百分比
        return max(-1.0, min(1.0, improvement))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'bottleneck_type': self.bottleneck_type.value,
            'priority': self.priority.value,
            'estimated_effort': self.estimated_effort,
            'expected_improvement': self.expected_improvement,
            'actual_improvement': self.actual_improvement,
            'owner': self.owner,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'bottlenecks': [b.to_dict() for b in self.bottlenecks],
            'metrics_before': self.metrics_before,
            'metrics_after': self.metrics_after
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizationPlan":
        """从 Redis / API 字典恢复方案对象。"""
        plan = cls(
            title=data.get('title', ''),
            description=data.get('description', ''),
            bottleneck_type=BottleneckType(data['bottleneck_type']),
            priority=OptimizationPriority(data['priority']),
            estimated_effort=int(data.get('estimated_effort', 0)),
            expected_improvement=float(data.get('expected_improvement', 0)),
            owner=data.get('owner', ''),
        )
        plan.id = data.get('id', plan.id)
        plan.status = OptimizationStatus(data.get('status', OptimizationStatus.PENDING.value))
        plan.actual_improvement = float(data.get('actual_improvement', 0))
        plan.metrics_before = data.get('metrics_before') or {}
        plan.metrics_after = data.get('metrics_after') or {}

        def _parse_ts(key: str):
            raw = data.get(key)
            if not raw:
                return None
            return dt.fromisoformat(raw)

        plan.created_at = _parse_ts('created_at') or plan.created_at
        plan.updated_at = _parse_ts('updated_at') or plan.updated_at
        plan.approved_at = _parse_ts('approved_at')
        plan.completed_at = _parse_ts('completed_at')
        plan.verified_at = _parse_ts('verified_at')
        return plan


# ====== 性能优化管理器 ======
class PerformanceOptimizationManager:
    """
    性能优化闭环管理器单例：基于 system_monitor 实时指标检测瓶颈并维护优化方案。

    与 SystemMonitor 类似使用双重检查锁保证多线程下单例；
    detect_bottlenecks 读取监控快照，不直接持有监控器写锁。
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
        """初始化优化方案与瓶颈记录存储。"""
        self.optimization_plans: Dict[str, OptimizationPlan] = {}
        self.bottlenecks: List[BottleneckRecord] = []
        self.max_bottlenecks = 1000
        self._redis_hydrated = False
        self._redis_hydrate_lock: Optional[asyncio.Lock] = None

    async def ensure_hydrated_from_redis(self) -> None:
        """
        从 Redis 加载优化方案与瓶颈记录（多 Worker 共享；单进程内仅执行一次）。

        使用 asyncio.Lock 双重检查，避免并发协程重复加载。
        Lock 仅在 async 上下文中惰性创建，避免同步路径触发「无运行中事件循环」错误。
        """
        if self._redis_hydrated:
            return
        if self._redis_hydrate_lock is None:
            self._redis_hydrate_lock = asyncio.Lock()
        async with self._redis_hydrate_lock:
            if self._redis_hydrated:
                return
            from app.core.optimization_store import load_bottlenecks_from_redis, load_plans_from_redis

            plans_data = await load_plans_from_redis()
            for plan_id, payload in plans_data.items():
                try:
                    self.optimization_plans[plan_id] = OptimizationPlan.from_dict(payload)
                except (KeyError, ValueError) as exc:
                    logger.warning("跳过无效优化方案 %s: %s", plan_id, exc)

            for item in await load_bottlenecks_from_redis(self.max_bottlenecks):
                try:
                    record = BottleneckRecord(
                        bottleneck_type=BottleneckType(item['bottleneck_type']),
                        metric_name=item['metric_name'],
                        current_value=float(item['current_value']),
                        threshold=float(item['threshold']),
                        description=item.get('description', ''),
                        timestamp=dt.fromisoformat(item['timestamp']) if item.get('timestamp') else None,
                    )
                    record.optimization_plan_id = item.get('optimization_plan_id')
                    self.bottlenecks.append(record)
                except (KeyError, ValueError) as exc:
                    logger.debug("跳过无效瓶颈记录: %s", exc)

            self._redis_hydrated = True

    def _schedule_async_persist(self, coro, *, context: str) -> None:
        """在运行中的事件循环上调度 Redis 持久化；无 loop 时记录降级日志。"""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            logger.debug(
                "%s Redis 持久化跳过：当前不在 async 事件循环中，"
                "数据仅保留在本进程内存（多 Worker 不共享）",
                context,
            )

    def _persist_plan_async(self, plan: OptimizationPlan) -> None:
        from app.core.optimization_store import save_plan_to_redis

        self._schedule_async_persist(
            save_plan_to_redis(plan.id, plan.to_dict()),
            context="优化方案",
        )

    def _persist_bottleneck_async(self, record: BottleneckRecord) -> None:
        from app.core.optimization_store import append_bottleneck_to_redis

        self._schedule_async_persist(
            append_bottleneck_to_redis(record.to_dict()),
            context="瓶颈记录",
        )
    
    # ====== 瓶颈检测 ======
    
    def detect_bottlenecks(self) -> List[BottleneckRecord]:
        """
        检测系统性能瓶颈
        
        Returns:
            检测到的瓶颈列表
        """
        bottlenecks = []
        metrics = self._get_current_metrics()
        
        # 检测API响应时间瓶颈
        if metrics['api.response_time_p99'] > 5.0:
            bottlenecks.append(BottleneckRecord(
                bottleneck_type=BottleneckType.API_RESPONSE_TIME,
                metric_name='api.response_time_p99',
                current_value=metrics['api.response_time_p99'],
                threshold=5.0,
                description=f"P99响应时间过高: {metrics['api.response_time_p99']:.2f}s"
            ))
        
        # 检测错误率瓶颈
        if metrics['api.error_rate'] > 0.05:
            bottlenecks.append(BottleneckRecord(
                bottleneck_type=BottleneckType.HIGH_ERROR_RATE,
                metric_name='api.error_rate',
                current_value=metrics['api.error_rate'],
                threshold=0.05,
                description=f"错误率过高: {metrics['api.error_rate']:.2%}"
            ))
        
        # 检测CPU使用率瓶颈
        if metrics['system.cpu_usage'] > 80.0:
            bottlenecks.append(BottleneckRecord(
                bottleneck_type=BottleneckType.HIGH_CPU_USAGE,
                metric_name='system.cpu_usage',
                current_value=metrics['system.cpu_usage'],
                threshold=80.0,
                description=f"CPU使用率过高: {metrics['system.cpu_usage']:.1f}%"
            ))
        
        # 检测内存使用率瓶颈
        if metrics['system.memory_usage'] > 85.0:
            bottlenecks.append(BottleneckRecord(
                bottleneck_type=BottleneckType.HIGH_MEMORY_USAGE,
                metric_name='system.memory_usage',
                current_value=metrics['system.memory_usage'],
                threshold=85.0,
                description=f"内存使用率过高: {metrics['system.memory_usage']:.1f}%"
            ))
        
        # 检测慢请求率瓶颈
        if metrics['api.slow_request_rate'] > 0.1:
            bottlenecks.append(BottleneckRecord(
                bottleneck_type=BottleneckType.API_RESPONSE_TIME,
                metric_name='api.slow_request_rate',
                current_value=metrics['api.slow_request_rate'],
                threshold=0.1,
                description=f"慢请求率过高: {metrics['api.slow_request_rate']:.1%}"
            ))
        
        # 保存检测到的瓶颈
        for b in bottlenecks:
            self.bottlenecks.append(b)
            if len(self.bottlenecks) > self.max_bottlenecks:
                self.bottlenecks.pop(0)
            self._persist_bottleneck_async(b)
        
        return bottlenecks
    
    def _get_current_metrics(self) -> Dict[str, float]:
        """获取当前所有指标"""
        return build_flat_monitoring_metrics(
            system_monitor.get_overall_api_stats(),
            system_monitor.get_resource_stats(),
        )
    
    # ====== 优化方案管理 ======
    
    def create_optimization_plan(self, title: str, description: str, 
                                 bottleneck_type: BottleneckType,
                                 priority: OptimizationPriority,
                                 estimated_effort: int,
                                 expected_improvement: float,
                                 owner: str = "") -> OptimizationPlan:
        """
        创建优化方案
        
        Args:
            title: 方案标题
            description: 方案描述
            bottleneck_type: 瓶颈类型
            priority: 优先级
            estimated_effort: 预估工时（小时）
            expected_improvement: 预期改进百分比
            owner: 负责人
        
        Returns:
            创建的优化方案
        """
        plan = OptimizationPlan(
            title=title,
            description=description,
            bottleneck_type=bottleneck_type,
            priority=priority,
            estimated_effort=estimated_effort,
            expected_improvement=expected_improvement,
            owner=owner
        )
        self.optimization_plans[plan.id] = plan
        self._persist_plan_async(plan)
        logger.info(f"【性能优化】已创建优化方案: {plan.title}")
        return plan
    
    def get_optimization_plan(self, plan_id: str) -> Optional[OptimizationPlan]:
        """获取优化方案"""
        return self.optimization_plans.get(plan_id)
    
    def get_all_optimization_plans(self, status: Optional[OptimizationStatus] = None) -> List[OptimizationPlan]:
        """
        获取所有优化方案
        
        Args:
            status: 状态过滤
        
        Returns:
            优化方案列表
        """
        plans = list(self.optimization_plans.values())
        if status:
            plans = [p for p in plans if p.status == status]
        plans.sort(key=lambda x: x.created_at, reverse=True)
        return plans
    
    def delete_optimization_plan(self, plan_id: str) -> bool:
        """删除优化方案"""
        if plan_id in self.optimization_plans:
            del self.optimization_plans[plan_id]
            try:
                loop = asyncio.get_running_loop()
                from app.core.optimization_store import delete_plan_from_redis
                loop.create_task(delete_plan_from_redis(plan_id))
            except RuntimeError:
                pass
            logger.info(f"【性能优化】已删除优化方案: {plan_id}")
            return True
        return False
    
    # ====== 优化效果分析 ======
    
    def analyze_optimization_effectiveness(self) -> Dict[str, Any]:
        """
        分析整体优化效果
        
        Returns:
            优化效果分析报告
        """
        all_plans = self.get_all_optimization_plans()
        verified_plans = [p for p in all_plans if p.status == OptimizationStatus.VERIFIED]
        
        # 统计数据
        stats = {
            'total_plans': len(all_plans),
            'pending_plans': len([p for p in all_plans if p.status == OptimizationStatus.PENDING]),
            'approved_plans': len([p for p in all_plans if p.status == OptimizationStatus.APPROVED]),
            'implementing_plans': len([p for p in all_plans if p.status == OptimizationStatus.IMPLEMENTING]),
            'completed_plans': len([p for p in all_plans if p.status == OptimizationStatus.COMPLETED]),
            'verified_plans': len(verified_plans),
            'rejected_plans': len([p for p in all_plans if p.status == OptimizationStatus.REJECTED])
        }
        
        # 计算整体改进效果
        if verified_plans:
            avg_expected_improvement = sum(p.expected_improvement for p in verified_plans) / len(verified_plans)
            avg_actual_improvement = sum(p.actual_improvement for p in verified_plans) / len(verified_plans)
            total_effort = sum(p.estimated_effort for p in verified_plans)
            
            stats.update({
                'avg_expected_improvement': avg_expected_improvement,
                'avg_actual_improvement': avg_actual_improvement,
                'total_effort_hours': total_effort,
                'plans': [p.to_dict() for p in verified_plans]
            })
        else:
            stats.update({
                'avg_expected_improvement': 0.0,
                'avg_actual_improvement': 0.0,
                'total_effort_hours': 0,
                'plans': [],
            })
        
        return stats
    
    def get_bottlenecks(self, limit: int = 50) -> List[BottleneckRecord]:
        """获取瓶颈记录列表"""
        return self.bottlenecks[-limit:][::-1]  # 倒序，最新的在前


# ====== 全局优化管理器实例 ======
optimization_manager = PerformanceOptimizationManager()


# ====== 定期检测任务 ======
async def start_bottleneck_detection():
    """
    启动定期瓶颈检测任务
    
    每5分钟检测一次系统性能瓶颈
    """
    try:
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟检测一次
            except asyncio.CancelledError:
                logger.debug("【性能优化】瓶颈检测任务已取消")
                raise
            bottlenecks = optimization_manager.detect_bottlenecks()

            if bottlenecks:
                logger.warning(f"【性能优化】检测到 {len(bottlenecks)} 个性能瓶颈")
                for b in bottlenecks:
                    logger.warning(f"  - {b.bottleneck_type.value}: {b.description}")
    except asyncio.CancelledError:
        logger.debug("【性能优化】定期检测任务已停止")
        raise


# ====== 优化路由 ======
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.security import require_admin


class OptimizationPlanCreateBody(BaseModel):
    """前端创建优化方案请求体。"""
    title: str
    description: str
    bottleneck_type: str
    priority: str = OptimizationPriority.MEDIUM.value
    estimated_effort: int = 8
    expected_improvement: float = 0.2
    owner: str = ""


class OptimizationPlanRejectBody(BaseModel):
    """前端拒绝优化方案请求体。"""
    reason: str = ""


optimization_router = APIRouter(tags=["性能优化"], dependencies=[Depends(require_admin)])


@optimization_router.get("/bottlenecks", summary="获取瓶颈列表")
async def get_bottlenecks(limit: int = Query(50, ge=1, le=200)):
    """
    获取检测到的性能瓶颈列表
    
    Args:
        limit: 返回数量限制
    """
    bottlenecks = optimization_manager.get_bottlenecks(limit)
    return [b.to_dict() for b in bottlenecks]


@optimization_router.post("/bottlenecks/detect", summary="手动检测瓶颈")
async def detect_bottlenecks():
    """手动触发瓶颈检测"""
    bottlenecks = optimization_manager.detect_bottlenecks()
    return {
        'message': f"检测完成，发现 {len(bottlenecks)} 个瓶颈",
        'bottlenecks': [b.to_dict() for b in bottlenecks]
    }


@optimization_router.get("/plans", summary="获取优化方案列表")
async def get_optimization_plans(
    status: Optional[str] = Query(None, enum=[s.value for s in OptimizationStatus])
):
    """
    获取优化方案列表
    
    Args:
        status: 状态过滤
    """
    status_enum = OptimizationStatus(status) if status else None
    plans = optimization_manager.get_all_optimization_plans(status_enum)
    return [p.to_dict() for p in plans]


@optimization_router.get("/plans/{plan_id}", summary="获取优化方案详情")
async def get_optimization_plan(plan_id: str):
    """
    获取单个优化方案详情
    
    Args:
        plan_id: 方案ID
    """
    plan = optimization_manager.get_optimization_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="方案不存在")
    return plan.to_dict()


@optimization_router.post("/plans", summary="创建优化方案")
async def create_optimization_plan(body: OptimizationPlanCreateBody):
    """
    创建新的优化方案（接受 JSON 请求体，与前端 PerformanceOptimization 一致）
    """
    try:
        bottleneck_enum = BottleneckType(body.bottleneck_type)
        priority_enum = OptimizationPriority(body.priority)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"无效参数: {e}")
    
    plan = optimization_manager.create_optimization_plan(
        title=body.title,
        description=body.description,
        bottleneck_type=bottleneck_enum,
        priority=priority_enum,
        estimated_effort=body.estimated_effort,
        expected_improvement=body.expected_improvement,
        owner=body.owner,
    )
    
    return plan.to_dict()


@optimization_router.put("/plans/{plan_id}/approve", summary="批准优化方案")
async def approve_optimization_plan(plan_id: str):
    """
    批准优化方案
    
    Args:
        plan_id: 方案ID
    """
    plan = optimization_manager.get_optimization_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="方案不存在")

    try:
        plan.approve()
        optimization_manager._persist_plan_async(plan)
        return plan.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@optimization_router.put("/plans/{plan_id}/start", summary="开始实施")
async def start_optimization_plan(plan_id: str):
    """
    开始实施优化方案
    
    Args:
        plan_id: 方案ID
    """
    plan = optimization_manager.get_optimization_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="方案不存在")

    try:
        plan.start_implementing()
        optimization_manager._persist_plan_async(plan)
        return plan.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@optimization_router.put("/plans/{plan_id}/complete", summary="完成实施")
async def complete_optimization_plan(plan_id: str):
    """
    完成优化方案实施
    
    Args:
        plan_id: 方案ID
    """
    plan = optimization_manager.get_optimization_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="方案不存在")

    try:
        plan.complete()
        optimization_manager._persist_plan_async(plan)
        return plan.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@optimization_router.put("/plans/{plan_id}/verify", summary="验证优化效果")
async def verify_optimization_plan(plan_id: str):
    """
    验证优化效果
    
    Args:
        plan_id: 方案ID
    """
    plan = optimization_manager.get_optimization_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="方案不存在")

    try:
        plan.verify()
        optimization_manager._persist_plan_async(plan)
        return plan.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@optimization_router.put("/plans/{plan_id}/reject", summary="拒绝优化方案")
async def reject_optimization_plan(
    plan_id: str,
    body: OptimizationPlanRejectBody | None = Body(default=None),
):
    """
    拒绝优化方案
    
    Args:
        plan_id: 方案ID
        body: 拒绝原因（JSON 请求体）
    """
    plan = optimization_manager.get_optimization_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="方案不存在")

    try:
        plan.reject(body.reason if body else "")
        optimization_manager._persist_plan_async(plan)
        return plan.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@optimization_router.delete("/plans/{plan_id}", summary="删除优化方案")
async def delete_optimization_plan(plan_id: str):
    """
    删除优化方案
    
    Args:
        plan_id: 方案ID
    """
    success = optimization_manager.delete_optimization_plan(plan_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="方案不存在")
    return {"message": "方案已删除"}


@optimization_router.get("/effectiveness", summary="分析优化效果")
async def analyze_effectiveness():
    """分析整体优化效果"""
    return optimization_manager.analyze_optimization_effectiveness()