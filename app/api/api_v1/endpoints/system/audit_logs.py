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
from app.core.security import require_admin, get_current_user, JWTUtils
from app.core.constants import MAX_PAGE_SIZE
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.dependencies import get_audit_log_service
from app.core.utils import get_client_ip
from app.models.models import UserAuditLog, User
from fastapi import Request
from app.schemas.audit_log import (
    UserAuditLogResponse,
    UserAuditLogQuery,
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.services.audit_log_service import AuditLogService

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


@router.get(
    "/",
    response_model=PaginatedResponseBaseSchema[list[UserAuditLogResponse]],
    summary="获取用户操作日志列表",
    description="查询用户操作日志，支持多种筛选条件，仅管理员可访问（已重构使用服务层）"
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
    获取用户操作日志列表（已重构使用服务层）
    
    支持以下筛选条件：
    - 用户ID/用户名
    - 操作类型（LOGIN, LOGOUT, CREATE, UPDATE, DELETE, VIEW, ACCESS等）
    - 资源类型（USER, CLIENT, PRODUCT, AD_DATA, SCHEDULED_TASK等）
    - IP地址
    - 操作是否成功
    - 时间范围
    """
    # 使用服务层（业务逻辑在AuditLogService中）
    audit_log_service: AuditLogService = await get_audit_log_service(db)
    
    try:
        # 调用服务层获取操作日志列表（服务层会处理查询、过滤、分页）
        logs, total = await audit_log_service.get_audit_logs(
            page=page,
            page_size=page_size,
            user_id=user_id,
            username=username,
            action_type=action_type,
            resource_type=resource_type,
            ip_address=ip_address,
            success=success,
            start_date=start_date,
            end_date=end_date
        )

        # 转换为响应模型
        log_responses = [
            UserAuditLogResponse.model_validate(log) for log in logs
        ]

        return PaginatedResponseBaseSchema.success(
            data=log_responses,
            total=total,
            page=page,
            page_size=page_size,
            message="获取日志列表成功"
        )

    except Exception as e:
        logger.error(f"获取用户操作日志列表失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取日志列表失败：{str(e)}"
        )


@router.get(
    "/stats/summary",
    response_model=ResponseBaseSchema[dict],
    summary="获取日志统计摘要",
    description="获取操作日志的统计信息，仅管理员可访问（已重构使用服务层）"
)
async def get_audit_log_stats(
        start_date: Optional[datetime] = Query(None, description="开始时间"),
        end_date: Optional[datetime] = Query(None, description="结束时间"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    获取日志统计摘要（已重构使用服务层）
    
    返回：
    - 总日志数
    - 成功/失败数量
    - 各操作类型数量
    - 各资源类型数量
    - 活跃用户数
    
    使用缓存提升性能（缓存 5 分钟）
    """
    # 使用服务层（业务逻辑在AuditLogService中）
    audit_log_service: AuditLogService = await get_audit_log_service(db)
    
    try:
        # 调用服务层获取日志统计摘要（服务层会处理查询、统计、缓存）
        stats = await audit_log_service.get_audit_log_stats(
            start_date=start_date,
            end_date=end_date
        )

        return ResponseBaseSchema.success(
            data=stats,
            message="获取统计信息成功"
        )

    except Exception as e:
        logger.error(f"获取日志统计信息失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取统计信息失败：{str(e)}"
        )


@router.get(
    "/{log_id}",
    response_model=ResponseBaseSchema[UserAuditLogResponse],
    summary="获取用户操作日志详情",
    description="根据日志ID获取详细信息，仅管理员可访问（已重构使用服务层）"
)
async def get_audit_log(
        log_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    获取用户操作日志详情（已重构使用服务层）
    """
    # 使用服务层（业务逻辑在AuditLogService中）
    audit_log_service: AuditLogService = await get_audit_log_service(db)
    
    try:
        # 调用服务层获取日志详情（服务层会处理查询）
        log = await audit_log_service.get_audit_log_by_id(log_id)

        if not log:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
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
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取日志详情失败: {str(e)}"
        )


@router.post(
    "/client-error",
    response_model=ResponseBaseSchema[dict],
    summary="记录客户端运行错误",
    description="记录前端JavaScript运行错误，所有用户可访问（包括未认证用户，已重构使用服务层）"
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
    记录客户端运行错误（已重构使用服务层）
    
    注意：此端点允许未认证用户访问，用于记录前端错误
    """
    # 使用服务层（业务逻辑在AuditLogService中）
    
    audit_log_service: AuditLogService = await get_audit_log_service(db)
    
    try:
        # 尝试获取当前用户（如果有认证信息）
        current_user = None
        username = None
        try:
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

        # 获取IP地址
        ip_address = get_client_ip(request)

        # 调用服务层记录客户端错误（服务层会处理错误信息截断和记录）
        await audit_log_service.log_client_error(
            error_type=error_type,
            error_message=error_message,
            error_stack=error_stack,
            error_url=error_url or request.url.path,
            user_agent=user_agent or request.headers.get("user-agent", ""),
            ip_address=ip_address,
            current_user=current_user,
            username=username
        )

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
