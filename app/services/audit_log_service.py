"""
用户操作审计日志服务层。

功能说明：
- 多维度筛选分页查询 ``UserAuditLog``（用户、操作类型、资源、时间、成功与否）
- 聚合统计操作类型/资源类型/成功率等，结果缓存 5 分钟减轻 Dashboard 压力
- 接收前端上报的运行时错误并写入审计表，便于关联用户操作与前端异常

在系统中的位置：
- 被管理端审计日志 API 与前端错误上报接口调用

注意事项：
1. 统计缓存键含 start_date/end_date，区间变更须自然失效
2. 审计日志可能含敏感参数，列表接口应脱敏或省略 request_body
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.audit_log import log_user_action, commit_audit_log
from app.core.infrastructure.cache_compat import (
    generate_cache_key,
    legacy_get_cached as get_cached,
    legacy_set_cached as set_cached,
)
from app.models.models import UserAuditLog, User

logger = logging.getLogger(__name__)


class AuditLogService:
    """
    审计日志服务。

    只读查询与 stats 聚合；log_client_error 为写路径，失败时 rollback 且不影响前端。
    """

    def __init__(self, db: AsyncSession):
        """注入异步数据库会话。"""
        self.db = db

    async def get_audit_logs(
            self,
            page: int = 1,
            page_size: int = 10,
            user_id: Optional[int] = None,
            username: Optional[str] = None,
            action_type: Optional[str] = None,
            resource_type: Optional[str] = None,
            ip_address: Optional[str] = None,
            success: Optional[bool] = None,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Tuple[List[UserAuditLog], int]:
        """
        分页查询审计日志。

        各筛选条件 AND 组合；默认按 created_at 降序。

        Args:
            page: 页码
            page_size: 每页条数
            user_id: 操作用户 ID
            username: 用户名模糊匹配
            action_type: 操作类型（如 CREATE、UPDATE）
            resource_type: 资源类型
            ip_address: 客户端 IP 精确匹配
            success: 是否成功
            start_date/end_date: 时间范围（闭区间端点由调用方约定）

        Returns:
            (日志列表, 总条数)
        """
        query = select(UserAuditLog)
        count_query = select(func.count(UserAuditLog.id))

        # 应用筛选条件
        conditions = []

        if user_id is not None:
            conditions.append(UserAuditLog.user_id == user_id)

        if username:
            conditions.append(UserAuditLog.username.ilike(f"%{username}%"))

        if action_type:
            conditions.append(UserAuditLog.action_type == action_type)

        if resource_type:
            conditions.append(UserAuditLog.resource_type == resource_type)

        if ip_address:
            conditions.append(UserAuditLog.ip_address == ip_address)

        if success is not None:
            conditions.append(UserAuditLog.success == success)

        if start_date:
            conditions.append(UserAuditLog.created_at >= start_date)

        if end_date:
            conditions.append(UserAuditLog.created_at <= end_date)

        # 应用所有条件
        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        # 获取总数
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 排序和分页
        query = query.order_by(UserAuditLog.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        # 执行查询
        result = await self.db.execute(query)
        logs = result.scalars().all()

        return logs, total

    async def get_audit_log_stats(
            self,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        获取审计日志统计摘要。

        含总量、成功/失败数、Top10 操作类型与资源类型、活跃用户数。
        相同时间范围命中缓存则直接返回（TTL 300s）。

        Args:
            start_date: 统计起始时间
            end_date: 统计结束时间

        Returns:
            聚合统计字典
        """
        # --- 缓存层：避免 Dashboard 频繁全表聚合 ---
        cache_key = generate_cache_key("audit_log_stats", start_date, end_date)
        cached = await get_cached(cache_key, key_prefix="audit_log")
        if cached:
            logger.debug("缓存命中: audit_log_stats")
            return cached

        # 构建基础查询
        base_query = select(UserAuditLog)
        conditions = []

        if start_date:
            conditions.append(UserAuditLog.created_at >= start_date)
        if end_date:
            conditions.append(UserAuditLog.created_at <= end_date)

        # --- 多维度 COUNT / GROUP BY 聚合 ---
        total_count_result = await self.db.execute(
            select(func.count(UserAuditLog.id)).where(
                and_(*conditions) if conditions else True
            )
        )
        total_count = total_count_result.scalar() or 0

        # 成功/失败数量
        success_count_result = await self.db.execute(
            select(func.count(UserAuditLog.id)).where(
                and_(
                    UserAuditLog.success == True,
                    *conditions if conditions else []
                )
            )
        )
        success_count = success_count_result.scalar() or 0

        failure_count_result = await self.db.execute(
            select(func.count(UserAuditLog.id)).where(
                and_(
                    UserAuditLog.success == False,
                    *conditions if conditions else []
                )
            )
        )
        failure_count = failure_count_result.scalar() or 0

        # 各操作类型数量（前10）
        action_type_result = await self.db.execute(
            select(
                UserAuditLog.action_type,
                func.count(UserAuditLog.id).label("count")
            )
            .where(and_(*conditions) if conditions else True)
            .group_by(UserAuditLog.action_type)
            .order_by(func.count(UserAuditLog.id).desc())
            .limit(10)
        )
        action_type_stats = {
            row.action_type: row.count
            for row in action_type_result.all()
        }

        # 各资源类型数量（前10）
        resource_type_result = await self.db.execute(
            select(
                UserAuditLog.resource_type,
                func.count(UserAuditLog.id).label("count")
            )
            .where(and_(*conditions) if conditions else True)
            .group_by(UserAuditLog.resource_type)
            .order_by(func.count(UserAuditLog.id).desc())
            .limit(10)
        )
        resource_type_stats = {
            row.resource_type: row.count
            for row in resource_type_result.all()
            if row.resource_type
        }

        # 活跃用户数（有操作记录的用户）
        active_users_result = await self.db.execute(
            select(func.count(func.distinct(UserAuditLog.user_id)))
            .where(
                and_(
                    UserAuditLog.user_id.isnot(None),
                    *conditions if conditions else []
                )
            )
        )
        active_users_count = active_users_result.scalar() or 0

        stats = {
            "total_count": total_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "action_type_stats": action_type_stats,
            "resource_type_stats": resource_type_stats,
            "active_users_count": active_users_count
        }

        # 缓存结果（缓存 5 分钟）
        await set_cached(cache_key, stats, ttl=300, key_prefix="audit_log")

        return stats

    async def get_audit_log_by_id(self, log_id: int) -> Optional[UserAuditLog]:
        """
        按主键获取单条审计日志。

        Args:
            log_id: 日志 ID

        Returns:
            UserAuditLog 或 None
        """
        result = await self.db.execute(
            select(UserAuditLog).where(UserAuditLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def log_client_error(
            self,
            error_type: str,
            error_message: str,
            error_stack: Optional[str] = None,
            error_url: Optional[str] = None,
            user_agent: Optional[str] = None,
            ip_address: Optional[str] = None,
            current_user: Optional[User] = None,
            username: Optional[str] = None
    ) -> None:
        """
        记录前端运行时错误到审计表。

        action_type=RUNTIME_ERROR，resource_type=FRONTEND；消息与堆栈截断以防过大。
        写入失败仅打 warning，不向上抛出，避免错误上报链路递归失败。

        Args:
            error_type: 错误分类（默认 JavaScriptError）
            error_message: 错误消息
            error_stack: 堆栈（可选）
            error_url: 发生页面 URL
            user_agent: UA 字符串
            ip_address: 客户端 IP
            current_user: 已登录用户（可选）
            username: 未登录时的用户名占位（可选）
        """

        # 截断超长字段，控制单行 audit 体积
        max_error_length = 1000
        truncated_error = error_message[:max_error_length] if len(error_message) > max_error_length else error_message

        # 限制堆栈长度
        max_stack_length = 2000
        truncated_stack = None
        if error_stack:
            truncated_stack = error_stack[:max_stack_length] if len(error_stack) > max_stack_length else error_stack

        try:
            await log_user_action(
                db=self.db,
                action_type="RUNTIME_ERROR",
                user=current_user,
                username=username,
                resource_type="FRONTEND",
                resource_name=error_url or "unknown",
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else None,
                success=False,
                error_message=truncated_error,
                details={
                    "error_type": error_type or "JavaScriptError",
                    "url": error_url or "unknown",
                    "user_agent": user_agent or "",
                    "stack_trace": truncated_stack
                }
            )
            await commit_audit_log(self.db)
        except Exception as e:
            # 记录错误日志失败不应该影响前端，静默处理
            logger.warning(f"记录客户端错误日志失败: {e}")
            await self.db.rollback()
