"""
用户操作日志API端点
提供用户操作日志的查询功能，仅管理员可访问
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from datetime import datetime
from typing import Optional
import logging

from app.core.database import get_db
from app.core.security import require_admin, get_current_user
from app.core.constants import MAX_PAGE_SIZE
from app.models.models import UserAuditLog, User
from fastapi import Request
from app.schemas.audit_log import (
    UserAuditLogResponse,
    UserAuditLogQuery,
    AuditLogListResponse
)
from app.schemas.base import ResponseBaseSchema

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


@router.get(
    "/",
    response_model=AuditLogListResponse,
    summary="获取用户操作日志列表",
    description="查询用户操作日志，支持多种筛选条件，仅管理员可访问"
)
async def get_audit_logs(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页数量"),
        user_id: Optional[int] = Query(None, description="用户ID筛选"),
        username: Optional[str] = Query(None, max_length=50, description="用户名筛选"),
        action_type: Optional[str] = Query(None, max_length=50, description="操作类型筛选"),
        resource_type: Optional[str] = Query(None, max_length=50, description="资源类型筛选"),
        ip_address: Optional[str] = Query(None, max_length=50, description="IP地址筛选"),
        success: Optional[bool] = Query(None, description="是否成功筛选"),
        start_date: Optional[datetime] = Query(None, description="开始时间"),
        end_date: Optional[datetime] = Query(None, description="结束时间"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    获取用户操作日志列表
    
    支持以下筛选条件：
    - 用户ID/用户名
    - 操作类型（LOGIN, LOGOUT, CREATE, UPDATE, DELETE, VIEW, ACCESS等）
    - 资源类型（USER, CLIENT, PRODUCT, AD_DATA, SCHEDULED_TASK等）
    - IP地址
    - 操作是否成功
    - 时间范围
    """
    try:
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
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # 排序和分页
        query = query.order_by(UserAuditLog.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        # 执行查询
        result = await db.execute(query)
        logs = result.scalars().all()

        # 转换为响应模型
        log_responses = [
            UserAuditLogResponse.model_validate(log) for log in logs
        ]

        return AuditLogListResponse.success(
            data=log_responses,
            total=total,
            page=page,
            page_size=page_size,
            message="获取日志列表成功"
        )

    except Exception as e:
        logger.error(f"获取用户操作日志列表失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取日志列表失败: {str(e)}"
        )


@router.get(
    "/stats/summary",
    response_model=ResponseBaseSchema[dict],
    summary="获取日志统计摘要",
    description="获取操作日志的统计信息，仅管理员可访问"
)
async def get_audit_log_stats(
        start_date: Optional[datetime] = Query(None, description="开始时间"),
        end_date: Optional[datetime] = Query(None, description="结束时间"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    获取日志统计摘要
    
    返回：
    - 总日志数
    - 成功/失败数量
    - 各操作类型数量
    - 各资源类型数量
    - 活跃用户数
    
    使用缓存提升性能（缓存 5 分钟）
    """
    try:
        # ====== 缓存优化 ======
        from app.core.cache import get_cached, set_cached, generate_cache_key
        cache_key = generate_cache_key("audit_log_stats", start_date, end_date)
        cached = await get_cached(cache_key)
        if cached:
            logger.debug("缓存命中: audit_log_stats")
            return ResponseBaseSchema.success(data=cached, message="获取统计信息成功")
        
        # 构建基础查询
        base_query = select(UserAuditLog)
        conditions = []

        if start_date:
            conditions.append(UserAuditLog.created_at >= start_date)
        if end_date:
            conditions.append(UserAuditLog.created_at <= end_date)

        if conditions:
            base_query = base_query.where(and_(*conditions))

        # 总日志数
        total_count_result = await db.execute(
            select(func.count(UserAuditLog.id)).where(
                and_(*conditions) if conditions else True
            )
        )
        total_count = total_count_result.scalar() or 0

        # 成功/失败数量
        success_count_result = await db.execute(
            select(func.count(UserAuditLog.id)).where(
                and_(
                    UserAuditLog.success == True,
                    *conditions if conditions else []
                )
            )
        )
        success_count = success_count_result.scalar() or 0

        failure_count_result = await db.execute(
            select(func.count(UserAuditLog.id)).where(
                and_(
                    UserAuditLog.success == False,
                    *conditions if conditions else []
                )
            )
        )
        failure_count = failure_count_result.scalar() or 0

        # 各操作类型数量（前10）
        action_type_result = await db.execute(
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
        resource_type_result = await db.execute(
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
        active_users_result = await db.execute(
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

        return ResponseBaseSchema.success(
            data=stats,
            message="获取统计信息成功"
        )

    except Exception as e:
        logger.error(f"获取日志统计信息失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计信息失败: {str(e)}"
        )


@router.get(
    "/{log_id}",
    response_model=ResponseBaseSchema[UserAuditLogResponse],
    summary="获取用户操作日志详情",
    description="根据日志ID获取详细信息，仅管理员可访问"
)
async def get_audit_log(
        log_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    获取用户操作日志详情
    """
    try:
        result = await db.execute(
            select(UserAuditLog).where(UserAuditLog.id == log_id)
        )
        log = result.scalar_one_or_none()

        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="日志记录不存在"
            )

        return ResponseBaseSchema.success(
            data=UserAuditLogResponse.model_validate(log),
            message="获取日志详情成功"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取用户操作日志详情失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取日志详情失败: {str(e)}"
        )


@router.post(
    "/client-error",
    response_model=ResponseBaseSchema[dict],
    summary="记录客户端运行错误",
    description="记录前端JavaScript运行错误，所有用户可访问（包括未认证用户）"
)
async def log_client_error(
        request: Request,
        error_type: str = Query(..., description="错误类型"),
        error_message: str = Query(..., description="错误信息"),
        error_stack: Optional[str] = Query(None, description="错误堆栈"),
        error_url: Optional[str] = Query(None, description="错误发生的URL"),
        user_agent: Optional[str] = Query(None, description="用户代理"),
        db: AsyncSession = Depends(get_db)
):
    """
    记录客户端运行错误
    
    注意：此端点允许未认证用户访问，用于记录前端错误
    """
    try:
        from app.core.audit_log import log_runtime_error

        # 尝试获取当前用户（如果有认证信息）
        current_user = None
        username = None
        try:
            from app.core.security import JWTUtils
            from sqlalchemy.future import select

            # 从请求头中获取token
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "")
                if token:
                    # verify_token 是异步方法，需要使用 await
                    payload = await JWTUtils.verify_token(token, db=db)
                    if payload and "sub" in payload:
                        user_id = payload.get("sub")
                        if user_id:
                            try:
                                user_id_int = int(user_id)
                                result = await db.execute(select(User).where(User.id == user_id_int))
                                current_user = result.scalar_one_or_none()
                                if current_user:
                                    username = current_user.username
                            except (ValueError, Exception):
                                pass
        except Exception:
            # 如果无法获取用户，继续使用 None（允许未认证用户记录错误）
            pass

        # 限制错误信息长度
        max_error_length = 1000
        truncated_error = error_message[:max_error_length] if len(error_message) > max_error_length else error_message

        # 限制堆栈长度
        max_stack_length = 2000
        truncated_stack = None
        if error_stack:
            truncated_stack = error_stack[:max_stack_length] if len(error_stack) > max_stack_length else error_stack

        await log_runtime_error(
            db=db,
            error_type=error_type or "JavaScriptError",
            error_message=truncated_error,
            request=request,
            user=current_user,
            username=username,
            resource_type="FRONTEND",
            resource_name=error_url or request.url.path,
            details={
                "url": error_url or request.url.path,
                "user_agent": user_agent or request.headers.get("user-agent", ""),
                "stack_trace": truncated_stack
            }
        )
        await db.commit()

        return ResponseBaseSchema.success(
            data={"message": "错误日志已记录"},
            message="错误日志已记录"
        )

    except Exception as e:
        # 记录错误日志失败不应该影响前端，静默处理
        logger.warning(f"记录客户端错误日志失败: {e}")
        return ResponseBaseSchema.success(
            data={"message": "错误日志记录失败"},
            message="错误日志记录失败"
        )
