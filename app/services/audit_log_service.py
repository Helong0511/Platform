"""
用户操作日志服务层
封装操作日志查询和统计的业务逻辑
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_

from app.models.models import UserAuditLog, User
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
import logging

logger = logging.getLogger(__name__)


class AuditLogService:
    """用户操作日志服务"""

    def __init__(self, db: AsyncSession):
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
        获取用户操作日志列表

        Args:
            page: 页码
            page_size: 每页数量
            user_id: 用户ID筛选
            username: 用户名筛选
            action_type: 操作类型筛选
            resource_type: 资源类型筛选
            ip_address: IP地址筛选
            success: 是否成功筛选
            start_date: 开始时间
            end_date: 结束时间

        Returns:
            Tuple[List[UserAuditLog], int]: (日志列表, 总数)
        """
        # 构建查询
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
        获取日志统计摘要

        Args:
            start_date: 开始时间
            end_date: 结束时间

        Returns:
            Dict: 统计信息
        """
        # ====== 缓存优化 ======
        from app.core.cache import get_cached, set_cached, generate_cache_key
        cache_key = generate_cache_key("audit_log_stats", start_date, end_date)
        cached = await get_cached(cache_key)
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

        # 总日志数
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
        await set_cached(cache_key, stats, ttl=300)

        return stats

    async def get_audit_log_by_id(self, log_id: int) -> Optional[UserAuditLog]:
        """
        获取用户操作日志详情

        Args:
            log_id: 日志ID

        Returns:
            Optional[UserAuditLog]: 日志对象，如果不存在则返回None
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
        记录客户端运行错误

        Args:
            error_type: 错误类型
            error_message: 错误信息
            error_stack: 错误堆栈
            error_url: 错误发生的URL
            user_agent: 用户代理
            ip_address: IP地址
            current_user: 当前用户（可选）
            username: 用户名（可选）
        """
        from app.core.audit_log import log_user_action

        # 限制错误信息长度
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
            await self.db.commit()
        except Exception as e:
            # 记录错误日志失败不应该影响前端，静默处理
            logger.warning(f"记录客户端错误日志失败: {e}")
            await self.db.rollback()

