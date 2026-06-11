"""系统管理模块路由聚合

职责：定时任务、审计日志、会话、通知配置、斗篷、缓存等运维能力。

权限：绝大多数端点需管理员。

说明：系统运维接口，含定时任务、审计日志、会话、缓存、斗篷与敏感路径探测。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。"""
from .scheduled_tasks import router as scheduled_tasks_router
from .audit_logs import router as audit_logs_router
from .sessions import router as sessions_router
from .notification_configs import router as notification_configs_router
from .third_party_reports import router as third_party_reports_router
from .cloak_configs import router as cloak_configs_router
from .sensitive_path_probes import router as sensitive_path_probes_router
from .cache_management import router as cache_management_router
from .countries import router as countries_router

__all__ = [
    'scheduled_tasks_router',
    'audit_logs_router',
    'sessions_router',
    'notification_configs_router',
    'third_party_reports_router',
    'cloak_configs_router',
    'sensitive_path_probes_router',
    'cache_management_router',
    'countries_router',
]

