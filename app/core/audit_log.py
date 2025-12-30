"""
用户操作日志记录工具
提供统一的日志记录接口，用于记录用户的各种操作
"""
import json
import logging
from datetime import datetime, date, timezone
from typing import Optional, Dict, Any
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import UserAuditLog, User
from app.core.utils import get_client_ip, get_app_now_naive

logger = logging.getLogger(__name__)

# 允许记录的操作类型白名单
ALLOWED_ACTION_TYPES = {
    "LOGIN",  # 登录
    "LOGOUT",  # 登出
    "CREATE",  # 增加
    "DELETE",  # 删除
    "UPDATE",  # 修改
    "IMPORT",  # 导入
    "EXPORT",  # 导出
    "ACTIVATE",  # 激活
    "DEACTIVATE",  # 禁用
    "TASK_RUN",  # 定时任务运行
    "API_ACCESS",  # 客户API访问
    "RUNTIME_ERROR",  # 程序运行错误
}


async def log_user_action(
        db: AsyncSession,
        action_type: str,
        user: Optional[User] = None,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        resource_name: Optional[str] = None,
        request: Optional[Request] = None,
        ip_address: Optional[str] = None,
        status_code: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request_params: Optional[Dict[str, Any]] = None
) -> None:
    """
    记录用户操作日志
    
    Args:
        db: 数据库会话
        action_type: 操作类型（LOGIN, LOGOUT, CREATE, UPDATE, DELETE, VIEW, ACCESS等）
        user: 用户对象（如果提供，会自动获取user_id和username）
        user_id: 用户ID（如果未提供user对象）
        username: 用户名（如果未提供user对象且未提供user_id，可直接指定用户名，如"SYSTEM"）
        resource_type: 资源类型（USER, CLIENT, PRODUCT, AD_DATA, SCHEDULED_TASK等）
        resource_id: 资源ID
        resource_name: 资源名称
        request: FastAPI请求对象（如果提供，会自动获取IP、路径等信息）
        ip_address: IP地址（如果未提供request对象）
        status_code: HTTP状态码
        success: 操作是否成功
        error_message: 错误信息
        details: 详细信息（字典格式，会自动转换为JSON）
        request_params: 请求参数（字典格式，会自动转换为JSON，不包含敏感信息）
    """
    # 检查操作类型是否在白名单中
    if action_type not in ALLOWED_ACTION_TYPES:
        # 不在白名单中的操作类型不记录日志
        logger.debug(f"操作类型 {action_type} 不在白名单中，跳过日志记录")
        return

    try:
        # 确定用户信息
        final_user_id = None
        final_username = None
        if user:
            final_user_id = user.id
            final_username = user.username
        elif user_id:
            final_user_id = user_id
            # 如果只提供了user_id，尝试查询用户名
            if not final_username:
                result = await db.execute(select(User).where(User.id == user_id))
                user_obj = result.scalar_one_or_none()
                if user_obj:
                    final_username = user_obj.username
        elif username:
            # 如果直接提供了username（如系统任务），使用提供的用户名
            final_username = username

        # 确定IP地址
        final_ip_address = ip_address
        if request and not final_ip_address:
            final_ip_address = get_client_ip(request)

        # 确定请求信息
        final_request_method = None
        final_request_path = None
        final_user_agent = None
        if request:
            final_request_method = request.method
            final_request_path = request.url.path
            final_user_agent = request.headers.get("user-agent", "")[:500]  # 限制长度

        # 处理请求参数（移除敏感信息）
        final_request_params = None
        if request_params:
            # 移除敏感字段
            sensitive_fields = {"password", "token", "secret", "key", "authorization"}
            filtered_params = {
                k: v for k, v in request_params.items()
                if k.lower() not in sensitive_fields
            }
            if filtered_params:
                try:
                    final_request_params = json.dumps(filtered_params, ensure_ascii=False)
                except (TypeError, ValueError):
                    final_request_params = str(filtered_params)[:1000]  # 限制长度

        # 处理详细信息
        final_details = None
        if details:
            try:
                # 将 details 中的日期对象转换为字符串，以便 JSON 序列化
                def convert_dates(obj):
                    """递归转换日期对象为字符串"""
                    if isinstance(obj, dict):
                        return {k: convert_dates(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [convert_dates(item) for item in obj]
                    elif isinstance(obj, (datetime, date)):
                        # 日期对象转换为 ISO 格式字符串
                        return obj.isoformat()
                    elif hasattr(obj, '__dict__'):
                        # 其他对象尝试转换为字典
                        return convert_dates(obj.__dict__)
                    else:
                        return obj
                
                # 转换日期对象
                converted_details = convert_dates(details)
                final_details = json.dumps(converted_details, ensure_ascii=False)
            except (TypeError, ValueError) as e:
                # 如果转换失败，尝试直接序列化
                try:
                    final_details = json.dumps(details, ensure_ascii=False, default=str)
                except:
                    final_details = str(details)[:1000]  # 限制长度

        # 创建日志记录
        audit_log = UserAuditLog(
            user_id=final_user_id,
            username=final_username,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            ip_address=final_ip_address,
            user_agent=final_user_agent,
            request_method=final_request_method,
            request_path=final_request_path,
            request_params=final_request_params,
            status_code=status_code,
            success=success,
            error_message=error_message[:1000] if error_message else None,  # 限制长度
            details=final_details,
            created_at=get_app_now_naive()  # 使用北京时间
        )

        db.add(audit_log)
        # 注意：这里不commit，由调用者决定何时commit
        # 这样可以与业务操作在同一个事务中

        # 记录调试信息（仅在DEBUG级别）
        logger.debug(
            f"审计日志已添加到会话: action_type={action_type}, "
            f"username={final_username}, resource_type={resource_type}, "
            f"resource_name={resource_name}, success={success}"
        )

    except Exception as e:
        # 日志记录失败不应该影响业务逻辑，但需要详细记录错误
        logger.error(
            f"记录用户操作日志失败: action_type={action_type}, "
            f"username={final_username}, resource_type={resource_type}, "
            f"error={e}",
            exc_info=True
        )


# 便捷函数
async def log_login(
        db: AsyncSession,
        user: User,
        request: Request,
        success: bool = True,
        error_message: Optional[str] = None
) -> None:
    """记录登录操作"""
    await log_user_action(
        db=db,
        action_type="LOGIN",
        user=user,
        request=request,
        success=success,
        error_message=error_message
    )


async def log_logout(
        db: AsyncSession,
        user: User,
        request: Request
) -> None:
    """记录登出操作"""
    await log_user_action(
        db=db,
        action_type="LOGOUT",
        user=user,
        request=request
    )


async def log_create(
        db: AsyncSession,
        user: User,
        resource_type: str,
        resource_id: int,
        resource_name: Optional[str] = None,
        request: Optional[Request] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
) -> None:
    """记录创建操作"""
    await log_user_action(
        db=db,
        action_type="CREATE",
        user=user,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        request=request,
        success=success,
        error_message=error_message,
        details=details
    )


async def log_update(
        db: AsyncSession,
        user: User,
        resource_type: str,
        resource_id: int,
        resource_name: Optional[str] = None,
        request: Optional[Request] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
) -> None:
    """记录更新操作"""
    await log_user_action(
        db=db,
        action_type="UPDATE",
        user=user,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        request=request,
        success=success,
        error_message=error_message,
        details=details
    )


async def log_delete(
        db: AsyncSession,
        user: User,
        resource_type: str,
        resource_id: int,
        resource_name: Optional[str] = None,
        request: Optional[Request] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
) -> None:
    """记录删除操作"""
    await log_user_action(
        db=db,
        action_type="DELETE",
        user=user,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        request=request,
        success=success,
        error_message=error_message,
        details=details
    )


async def log_activate(
        db: AsyncSession,
        user: User,
        resource_type: str,
        resource_id: int,
        resource_name: Optional[str] = None,
        request: Optional[Request] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
) -> None:
    """记录激活操作"""
    await log_user_action(
        db=db,
        action_type="ACTIVATE",
        user=user,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        request=request,
        success=success,
        error_message=error_message,
        details=details
    )


async def log_deactivate(
        db: AsyncSession,
        user: User,
        resource_type: str,
        resource_id: int,
        resource_name: Optional[str] = None,
        request: Optional[Request] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
) -> None:
    """记录禁用操作"""
    await log_user_action(
        db=db,
        action_type="DEACTIVATE",
        user=user,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        request=request,
        success=success,
        error_message=error_message,
        details=details
    )


async def log_runtime_error(
        db: AsyncSession,
        error_type: str,
        error_message: str,
        request: Optional[Request] = None,
        user: Optional[User] = None,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        resource_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
) -> None:
    """记录程序运行错误"""
    await log_user_action(
        db=db,
        action_type="RUNTIME_ERROR",
        user=user,
        user_id=user_id,
        username=username or "SYSTEM",
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        request=request,
        success=False,
        error_message=error_message,
        details={
            "error_type": error_type,
            **(details or {})
        }
    )
