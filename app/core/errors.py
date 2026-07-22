"""
统一错误码和错误信息定义
确保前后端错误处理的一致性
"""
import asyncio
import logging
import traceback
from enum import IntEnum
from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException, Request
from sqlalchemy.future import select

from app.core.audit_log import log_runtime_error
from app.core.database import AsyncSessionLocal
from app.core.telegram.runtime_error_notify import notify_runtime_error_async
from app.core.utils import get_client_ip, get_app_now_naive
from app.models.models import User


class ErrorCode(IntEnum):
    """API 错误码枚举"""
    # ====== 通用错误 (1000-1999) ======
    SUCCESS = 200  # 成功
    BAD_REQUEST = 400  # 请求参数错误
    UNAUTHORIZED = 401  # 未授权
    FORBIDDEN = 403  # 禁止访问
    NOT_FOUND = 404  # 资源不存在
    METHOD_NOT_ALLOWED = 405  # 方法不允许
    CONFLICT = 409  # 资源冲突
    VALIDATION_ERROR = 422  # 验证错误
    TOO_MANY_REQUESTS = 429  # 请求过于频繁
    INTERNAL_ERROR = 500  # 服务器内部错误
    SERVICE_UNAVAILABLE = 503  # 服务不可用

    # ====== 业务错误 (2000-2999) ======
    # 认证相关 (2000-2099)
    INVALID_CREDENTIALS = 2001  # 用户名或密码错误
    TOKEN_EXPIRED = 2002  # Token 已过期
    TOKEN_INVALID = 2003  # Token 无效
    USER_DISABLED = 2004  # 用户已被禁用

    # 用户相关 (2100-2199)
    USER_NOT_FOUND = 2101  # 用户不存在
    USER_ALREADY_EXISTS = 2102  # 用户已存在
    USERNAME_TAKEN = 2103  # 用户名已被使用
    EMAIL_TAKEN = 2104  # 邮箱已被使用

    # 客户相关 (2200-2299)
    CLIENT_NOT_FOUND = 2201  # 客户不存在
    CLIENT_ALREADY_EXISTS = 2202  # 客户已存在
    CLIENT_NO_PERMISSION = 2203  # 没有权限访问客户
    CLIENT_HAS_PRODUCTS = 2204  # 客户有关联产品，无法删除
    CLIENT_API_VALIDATION_FAILED = 2205  # 客户API参数验证失败

    # 产品相关 (2250-2299)
    PRODUCT_NOT_FOUND = 2251  # 产品不存在
    PRODUCT_ALREADY_EXISTS = 2252  # 产品已存在
    PRODUCT_NO_PERMISSION = 2253  # 没有权限访问产品
    PRODUCT_HAS_DATA = 2254  # 产品有关联数据，无法删除
    PRODUCT_DEDUCT_RATIO_INVALID = 2255  # 减扣比例无效
    PRODUCT_CLIENT_REQUIRED = 2256  # 创建产品必须指定客户ID

    # 广告数据相关 (2260-2279)
    AD_DATA_NOT_FOUND = 2261  # 广告数据不存在
    AD_DATA_NO_PERMISSION = 2262  # 没有权限访问广告数据
    AD_DATA_UPDATE_FORBIDDEN = 2263  # 仅管理员可更新广告数据
    AD_DATA_DELETE_FORBIDDEN = 2264  # 没有权限删除广告数据
    AD_DATA_PRODUCT_NOT_FOUND = 2265  # 关联的产品不存在
    AD_DATA_EMPTY_SELECTION = 2266  # 未选择要删除的数据

    # 定时任务相关 (2300-2399)
    TASK_NOT_FOUND = 2301  # 任务不存在
    TASK_ALREADY_EXISTS = 2302  # 任务已存在
    TASK_NAME_INVALID = 2303  # 任务名称无效
    TASK_IS_RUNNING = 2304  # 任务正在运行中
    TASK_CRON_INVALID = 2305  # Cron 表达式无效
    TASK_FUNCTION_NOT_FOUND = 2306  # 任务函数不存在

    # 数据导入相关 (2400-2499)
    IMPORT_FILE_INVALID = 2401  # 导入文件格式无效
    IMPORT_COLUMN_MAPPING_INCOMPLETE = 2402  # 列映射不完整
    IMPORT_DATA_VALIDATION_FAILED = 2403  # 数据验证失败
    IMPORT_DUPLICATE_DATA = 2404  # 重复数据

    # 其他业务错误 (2500-2999)
    OPERATION_FAILED = 2501  # 操作失败
    RESOURCE_LOCKED = 2502  # 资源被锁定
    CANNOT_DELETE_SELF = 2503  # 不能删除自己的账户
    CANNOT_MODIFY_SELF_ROLE = 2504  # 不能修改自己的角色
    USER_HAS_CLIENTS = 2505  # 用户有关联客户，无法删除
    NO_ADMIN_USERS = 2506  # 系统中没有管理员用户
    RESOURCE_NOT_FOUND = 2507  # 资源不存在
    RESOURCE_ALREADY_EXISTS = 2508  # 资源已存在
    ACCESS_DENIED = 2509  # 访问被拒绝
    INVALID_PARAMETER = 2510  # 参数无效


class ErrorMessage:
    """错误信息常量"""
    # 通用错误信息
    SUCCESS = "操作成功"
    BAD_REQUEST = "请求参数错误"
    UNAUTHORIZED = "未授权，请先登录"
    FORBIDDEN = "禁止访问，权限不足"
    NOT_FOUND = "资源不存在"
    METHOD_NOT_ALLOWED = "请求方法不允许"
    CONFLICT = "资源冲突"
    VALIDATION_ERROR = "数据验证失败"
    TOO_MANY_REQUESTS = "请求过于频繁，请稍后再试"
    INTERNAL_ERROR = "服务器内部错误"
    SERVICE_UNAVAILABLE = "服务暂时不可用"

    # 业务错误信息
    INVALID_CREDENTIALS = "用户名或密码错误"
    TOKEN_EXPIRED = "登录已过期，请重新登录"
    TOKEN_INVALID = "登录凭证无效，请重新登录"
    USER_DISABLED = "用户已被禁用"
    USER_NOT_FOUND = "用户不存在"
    USER_ALREADY_EXISTS = "用户已存在"
    USERNAME_TAKEN = "用户名已被使用"
    EMAIL_TAKEN = "邮箱已被使用"
    CLIENT_NOT_FOUND = "客户不存在"
    CLIENT_ALREADY_EXISTS = "客户已存在"
    CLIENT_NO_PERMISSION = "没有权限访问此客户"
    CLIENT_HAS_PRODUCTS = "客户有关联产品，无法删除"
    CLIENT_API_VALIDATION_FAILED = "参数验证不通过"

    PRODUCT_NOT_FOUND = "产品不存在"
    PRODUCT_ALREADY_EXISTS = "产品已存在"
    PRODUCT_NO_PERMISSION = "没有权限访问此产品"
    PRODUCT_HAS_DATA = "产品有关联广告数据，无法删除"
    PRODUCT_DEDUCT_RATIO_INVALID = "减扣比例必须在0到1之间"
    PRODUCT_CLIENT_REQUIRED = "创建产品必须指定客户ID"

    AD_DATA_NOT_FOUND = "广告数据不存在"
    AD_DATA_NO_PERMISSION = "没有权限访问此广告数据"
    AD_DATA_UPDATE_FORBIDDEN = "仅管理员可更新广告数据"
    AD_DATA_DELETE_FORBIDDEN = "没有权限删除此广告数据"
    AD_DATA_PRODUCT_NOT_FOUND = "关联的产品不存在"
    AD_DATA_EMPTY_SELECTION = "请选择要删除的数据"

    TASK_NOT_FOUND = "定时任务不存在"
    TASK_ALREADY_EXISTS = "定时任务已存在"
    TASK_NAME_INVALID = "任务名称无效"
    TASK_IS_RUNNING = "任务正在运行中，请稍后再试"
    TASK_CRON_INVALID = "Cron 表达式格式错误"
    TASK_FUNCTION_NOT_FOUND = "任务函数不存在"
    IMPORT_FILE_INVALID = "导入文件格式无效"
    IMPORT_COLUMN_MAPPING_INCOMPLETE = "列映射不完整"
    IMPORT_DATA_VALIDATION_FAILED = "数据验证失败"
    IMPORT_DUPLICATE_DATA = "存在重复数据"
    OPERATION_FAILED = "操作失败"
    RESOURCE_LOCKED = "资源被锁定"
    CANNOT_DELETE_SELF = "不能删除自己的账户"
    CANNOT_MODIFY_SELF_ROLE = "不能将自己的角色修改为非管理员"
    USER_HAS_CLIENTS = "用户有关联客户数据，无法删除"
    NO_ADMIN_USERS = "系统中没有管理员用户"
    RESOURCE_NOT_FOUND = "资源不存在"
    RESOURCE_ALREADY_EXISTS = "资源已存在"
    ACCESS_DENIED = "访问被拒绝"
    INVALID_PARAMETER = "参数无效"


def get_error_message(error_code: int, custom_message: Optional[str] = None) -> str:
    """
    获取错误信息
    
    Args:
        error_code: 错误码
        custom_message: 自定义错误信息（如果提供，优先使用）
    
    Returns:
        错误信息字符串
    """
    if custom_message:
        return custom_message

    # 根据错误码返回对应的错误信息
    error_code_map = {
        ErrorCode.SUCCESS: ErrorMessage.SUCCESS,
        ErrorCode.BAD_REQUEST: ErrorMessage.BAD_REQUEST,
        ErrorCode.UNAUTHORIZED: ErrorMessage.UNAUTHORIZED,
        ErrorCode.FORBIDDEN: ErrorMessage.FORBIDDEN,
        ErrorCode.NOT_FOUND: ErrorMessage.NOT_FOUND,
        ErrorCode.METHOD_NOT_ALLOWED: ErrorMessage.METHOD_NOT_ALLOWED,
        ErrorCode.CONFLICT: ErrorMessage.CONFLICT,
        ErrorCode.VALIDATION_ERROR: ErrorMessage.VALIDATION_ERROR,
        ErrorCode.TOO_MANY_REQUESTS: ErrorMessage.TOO_MANY_REQUESTS,
        ErrorCode.INTERNAL_ERROR: ErrorMessage.INTERNAL_ERROR,
        ErrorCode.SERVICE_UNAVAILABLE: ErrorMessage.SERVICE_UNAVAILABLE,
        ErrorCode.INVALID_CREDENTIALS: ErrorMessage.INVALID_CREDENTIALS,
        ErrorCode.TOKEN_EXPIRED: ErrorMessage.TOKEN_EXPIRED,
        ErrorCode.TOKEN_INVALID: ErrorMessage.TOKEN_INVALID,
        ErrorCode.USER_DISABLED: ErrorMessage.USER_DISABLED,
        ErrorCode.USER_NOT_FOUND: ErrorMessage.USER_NOT_FOUND,
        ErrorCode.USER_ALREADY_EXISTS: ErrorMessage.USER_ALREADY_EXISTS,
        ErrorCode.USERNAME_TAKEN: ErrorMessage.USERNAME_TAKEN,
        ErrorCode.EMAIL_TAKEN: ErrorMessage.EMAIL_TAKEN,
        ErrorCode.CLIENT_NOT_FOUND: ErrorMessage.CLIENT_NOT_FOUND,
        ErrorCode.CLIENT_ALREADY_EXISTS: ErrorMessage.CLIENT_ALREADY_EXISTS,
        ErrorCode.CLIENT_NO_PERMISSION: ErrorMessage.CLIENT_NO_PERMISSION,
        ErrorCode.CLIENT_HAS_PRODUCTS: ErrorMessage.CLIENT_HAS_PRODUCTS,
        ErrorCode.CLIENT_API_VALIDATION_FAILED: ErrorMessage.CLIENT_API_VALIDATION_FAILED,
        ErrorCode.PRODUCT_NOT_FOUND: ErrorMessage.PRODUCT_NOT_FOUND,
        ErrorCode.PRODUCT_ALREADY_EXISTS: ErrorMessage.PRODUCT_ALREADY_EXISTS,
        ErrorCode.PRODUCT_NO_PERMISSION: ErrorMessage.PRODUCT_NO_PERMISSION,
        ErrorCode.PRODUCT_HAS_DATA: ErrorMessage.PRODUCT_HAS_DATA,
        ErrorCode.PRODUCT_DEDUCT_RATIO_INVALID: ErrorMessage.PRODUCT_DEDUCT_RATIO_INVALID,
        ErrorCode.PRODUCT_CLIENT_REQUIRED: ErrorMessage.PRODUCT_CLIENT_REQUIRED,
        ErrorCode.AD_DATA_NOT_FOUND: ErrorMessage.AD_DATA_NOT_FOUND,
        ErrorCode.AD_DATA_NO_PERMISSION: ErrorMessage.AD_DATA_NO_PERMISSION,
        ErrorCode.AD_DATA_UPDATE_FORBIDDEN: ErrorMessage.AD_DATA_UPDATE_FORBIDDEN,
        ErrorCode.AD_DATA_DELETE_FORBIDDEN: ErrorMessage.AD_DATA_DELETE_FORBIDDEN,
        ErrorCode.AD_DATA_PRODUCT_NOT_FOUND: ErrorMessage.AD_DATA_PRODUCT_NOT_FOUND,
        ErrorCode.AD_DATA_EMPTY_SELECTION: ErrorMessage.AD_DATA_EMPTY_SELECTION,
        ErrorCode.TASK_NOT_FOUND: ErrorMessage.TASK_NOT_FOUND,
        ErrorCode.TASK_ALREADY_EXISTS: ErrorMessage.TASK_ALREADY_EXISTS,
        ErrorCode.TASK_NAME_INVALID: ErrorMessage.TASK_NAME_INVALID,
        ErrorCode.TASK_IS_RUNNING: ErrorMessage.TASK_IS_RUNNING,
        ErrorCode.TASK_CRON_INVALID: ErrorMessage.TASK_CRON_INVALID,
        ErrorCode.TASK_FUNCTION_NOT_FOUND: ErrorMessage.TASK_FUNCTION_NOT_FOUND,
        ErrorCode.IMPORT_FILE_INVALID: ErrorMessage.IMPORT_FILE_INVALID,
        ErrorCode.IMPORT_COLUMN_MAPPING_INCOMPLETE: ErrorMessage.IMPORT_COLUMN_MAPPING_INCOMPLETE,
        ErrorCode.IMPORT_DATA_VALIDATION_FAILED: ErrorMessage.IMPORT_DATA_VALIDATION_FAILED,
        ErrorCode.IMPORT_DUPLICATE_DATA: ErrorMessage.IMPORT_DUPLICATE_DATA,
        ErrorCode.OPERATION_FAILED: ErrorMessage.OPERATION_FAILED,
        ErrorCode.RESOURCE_LOCKED: ErrorMessage.RESOURCE_LOCKED,
        ErrorCode.CANNOT_DELETE_SELF: ErrorMessage.CANNOT_DELETE_SELF,
        ErrorCode.CANNOT_MODIFY_SELF_ROLE: ErrorMessage.CANNOT_MODIFY_SELF_ROLE,
        ErrorCode.USER_HAS_CLIENTS: ErrorMessage.USER_HAS_CLIENTS,
        ErrorCode.NO_ADMIN_USERS: ErrorMessage.NO_ADMIN_USERS,
        ErrorCode.RESOURCE_NOT_FOUND: ErrorMessage.RESOURCE_NOT_FOUND,
        ErrorCode.RESOURCE_ALREADY_EXISTS: ErrorMessage.RESOURCE_ALREADY_EXISTS,
        ErrorCode.ACCESS_DENIED: ErrorMessage.ACCESS_DENIED,
        ErrorCode.INVALID_PARAMETER: ErrorMessage.INVALID_PARAMETER,
    }

    return error_code_map.get(error_code, ErrorMessage.INTERNAL_ERROR)


# 错误解决方案建议映射
ERROR_SOLUTIONS = {
    ErrorCode.BAD_REQUEST: "请检查请求参数是否正确",
    ErrorCode.UNAUTHORIZED: "请先登录或重新登录获取访问凭证",
    ErrorCode.FORBIDDEN: "请联系管理员获取相应权限",
    ErrorCode.NOT_FOUND: "请确认资源ID或路径是否正确",
    ErrorCode.CONFLICT: "请检查资源是否已存在或数据是否冲突",
    ErrorCode.VALIDATION_ERROR: "请检查输入数据格式是否符合要求",
    ErrorCode.TOO_MANY_REQUESTS: "请稍后再试，避免频繁请求",
    ErrorCode.INTERNAL_ERROR: "请稍后重试，如果问题持续存在请联系技术支持",
    ErrorCode.SERVICE_UNAVAILABLE: "服务暂时不可用，请稍后重试",
    ErrorCode.INVALID_CREDENTIALS: "请检查用户名和密码是否正确",
    ErrorCode.TOKEN_EXPIRED: "请重新登录获取新的访问令牌",
    ErrorCode.TOKEN_INVALID: "请重新登录获取有效的访问令牌",
    ErrorCode.USER_DISABLED: "您的账户已被禁用，请联系管理员",
    ErrorCode.USER_NOT_FOUND: "请确认用户ID是否正确",
    ErrorCode.USER_ALREADY_EXISTS: "请使用其他用户名",
    ErrorCode.USERNAME_TAKEN: "请选择其他用户名",
    ErrorCode.EMAIL_TAKEN: "请使用其他邮箱地址",
    ErrorCode.CLIENT_NOT_FOUND: "请确认客户ID是否正确",
    ErrorCode.CLIENT_ALREADY_EXISTS: "该客户已存在",
    ErrorCode.PRODUCT_NOT_FOUND: "请确认产品ID是否正确",
    ErrorCode.PRODUCT_ALREADY_EXISTS: "该产品已存在",
    ErrorCode.OPERATION_FAILED: "请检查操作数据并重试",
    ErrorCode.RESOURCE_NOT_FOUND: "请确认资源是否存在",
    ErrorCode.RESOURCE_ALREADY_EXISTS: "请使用其他标识",
    ErrorCode.ACCESS_DENIED: "请联系管理员获取访问权限",
    ErrorCode.INVALID_PARAMETER: "请检查参数是否正确",
}

def get_error_solution(error_code: int) -> Optional[str]:
    """
    获取错误的解决方案建议
    
    Args:
        error_code: 错误码
    
    Returns:
        解决方案建议字符串或None
    """
    return ERROR_SOLUTIONS.get(error_code)

def create_error_response(
        error_code: int,
        message: Optional[str] = None,
        detail: Optional[str] = None,
        data: Optional[Any] = None,
        path: Optional[str] = None
) -> Dict[str, Any]:
    """
    创建标准错误响应
    
    Args:
        error_code: 错误码
        message: 错误信息（如果为 None，会根据 error_code 自动获取）
        detail: 详细错误信息（可选）
        data: 附加数据（可选）
        path: 请求路径（可选）
    
    Returns:
        标准错误响应字典
    """
    error_message = get_error_message(error_code, message)
    solution = get_error_solution(error_code)
    
    # 获取当前时间戳
    timestamp = get_app_now_naive().isoformat()
    
    # 构建响应状态
    status = "error"
    if error_code == ErrorCode.SUCCESS:
        status = "success"
    
    response = {
        "code": error_code,
        "status": status,
        "message": error_message,
        "timestamp": timestamp,
    }
    
    # 添加请求路径（如果提供）
    if path:
        response["path"] = path
    
    # 添加详细错误信息
    if detail:
        response["detail"] = detail
    
    # 添加解决方案建议
    if solution:
        response["solution"] = solution
    
    # 添加附加数据
    if data is not None:
        response["data"] = data
    
    return response


async def record_http_exception_log(
        exc: HTTPException,
        request: Request,
        error_type: str = "HTTPException"
) -> None:
    """
    记录 HTTPException 日志的公共函数
    用于统一处理 HTTPException 的日志记录逻辑
    
    增强功能：
    - 记录更详细的请求信息（方法、路径、参数、头部）
    - 记录用户信息（如果已认证）
    - 记录错误堆栈（如果是服务器错误）
    - 限制日志长度，防止日志过大
    
    Args:
        exc: HTTPException 异常对象
        request: 请求对象
        error_type: 错误类型（用于日志分类）
    """
    logger = logging.getLogger(__name__)
    
    # 只在 500/503 错误时记录日志
    if exc.status_code < 500:
        return
    
    async def record_error_log():
        """后台任务：将 5xx HTTPException 写入审计日志表（独立会话，不阻塞响应）。"""
        audit_db = None
        try:
            audit_db = AsyncSessionLocal()
            
            # 尝试从请求中获取当前用户
            current_user = None
            username = None
            try:
                token = request.headers.get("Authorization", "").replace("Bearer ", "")
                if token:
                    from app.core.security import JWTUtils

                    payload = await JWTUtils.verify_token(token)
                    if payload and "sub" in payload:
                        user_id = payload.get("sub")
                        if user_id:
                            try:
                                user_id_int = int(user_id)
                                result = await audit_db.execute(select(User).where(User.id == user_id_int))
                                current_user = result.scalar_one_or_none()
                                if current_user:
                                    username = current_user.username
                            except (ValueError, Exception):
                                pass
            except Exception:
                pass
            
            error_message = str(exc.detail) if hasattr(exc, 'detail') else str(exc)
            # 限制错误信息长度
            max_error_length = 1000
            truncated_error = error_message[:max_error_length] if len(error_message) > max_error_length else error_message
            
            # 收集详细的请求信息
            request_details = {
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code,
                "detail": exc.detail if hasattr(exc, 'detail') else str(exc),
                "query_params": str(request.query_params) if request.query_params else None,
                "client_ip": None,
                "user_agent": request.headers.get("User-Agent", None)
            }
            
            # 获取客户端IP
            try:
                request_details["client_ip"] = get_client_ip(request)
            except Exception:
                pass
            
            # 记录堆栈信息（如果是服务器错误）
            if exc.status_code >= 500:
                try:
                    # 尝试获取异常堆栈
                    if hasattr(exc, '__traceback__') and exc.__traceback__:
                        stack_trace = ''.join(traceback.format_exception(
                            type(exc), exc, exc.__traceback__
                        ))
                        # 限制堆栈长度
                        max_stack_length = 2000
                        request_details["stack_trace"] = (
                            stack_trace[:max_stack_length] 
                            if len(stack_trace) > max_stack_length 
                            else stack_trace
                        )
                except Exception:
                    pass
            
            await log_runtime_error(
                db=audit_db,
                error_type=f"{error_type}_{exc.status_code}",
                error_message=truncated_error,
                request=request,
                user=current_user,
                username=username,
                resource_type="SYSTEM",
                resource_name=request.url.path,
                details=request_details
            )
            await audit_db.commit()

            await notify_runtime_error_async(
                error_type=f"{error_type}_{exc.status_code}",
                error_message=truncated_error,
                location={
                    "module": "app.core.errors",
                    "function": "record_http_exception_log",
                },
                context={
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": exc.status_code,
                    "client_ip": request_details.get("client_ip"),
                },
                stack_trace=request_details.get("stack_trace"),
                logger_name="app.core.errors",
            )
        except Exception as log_error:
            logger.warning(f"记录{error_type}日志失败: {log_error}")
        finally:
            if audit_db:
                try:
                    await audit_db.close()
                except Exception:
                    pass
    
    # 在后台任务中记录日志
    try:
        asyncio.create_task(record_error_log())
    except Exception as e:
        logger.warning(f"启动{error_type}日志记录任务失败: {e}")