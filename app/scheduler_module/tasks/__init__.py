"""
定时任务函数包（部分清理类任务导出）。

功能说明：
- 导出会话清理、审计日志清理、敏感路径探测日志清理等维护类任务
- 其它上游拉数、转发类任务由 task_registry 按路径动态加载

在系统中的位置：
- 被 task_registry 自动扫描或显式 import 注册

注意事项：
1. 新增维护类任务若需统一导出，在此加入 __all__
2. 上游拉数任务通常只需在 task_config 填写 module 路径即可
"""
from app.scheduler_module.tasks.cleanup_expired_sessions import cleanup_expired_sessions
from app.scheduler_module.tasks.cleanup_old_logs import cleanup_old_audit_logs
from app.scheduler_module.tasks.cleanup_sensitive_path_probes import cleanup_sensitive_path_probe_logs

__all__ = [
    "cleanup_expired_sessions",
    "cleanup_old_audit_logs",
    "cleanup_sensitive_path_probe_logs",
]
