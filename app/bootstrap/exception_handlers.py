"""
FastAPI 全局异常处理器注册。

从 main.py 抽离，统一 Validation / HTTP / 未捕获异常的处理逻辑。
"""
import asyncio
import base64
import logging
import traceback

from anyio import EndOfStream
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.future import select

from app.core.audit_log import log_runtime_error
from app.core.config import settings
from app.core.constants import MAX_ERROR_MESSAGE_LENGTH, MAX_STACK_TRACE_LENGTH
from app.core.database import AsyncSessionLocal
from app.core.errors import ErrorCode, create_error_response, record_http_exception_log
from app.services.ad_data.queries.filter_conditions import InvalidFilterParameterError
from app.core.security import JWTUtils
from app.core.utils import get_client_ip
from app.models.models import User

logger = logging.getLogger(__name__)


def _is_stream_error(exc: Exception) -> bool:
    """
    检查异常是否是流关闭相关的异常（客户端提前关闭连接）
    
    Args:
        exc: 异常对象
    
    Returns:
        如果是流异常返回True，否则返回False
    """
    error_type = type(exc).__name__
    error_module = type(exc).__module__
    return ("EndOfStream" in error_type or "WouldBlock" in error_type or
            "anyio" in error_module)


def _check_connection_disconnected(request: Request) -> bool:
    """
    检查请求连接是否已断开
    
    Args:
        request: 请求对象
    
    Returns:
        如果连接已断开返回True，否则返回False
    """
    return hasattr(request, '_is_disconnected') and request._is_disconnected


def _raise_stream_error_if_disconnected(request: Request) -> None:
    """
    如果连接已断开，抛出流异常
    
    Args:
        request: 请求对象
    
    Raises:
        EndOfStream: 如果连接已断开
    """
    if _check_connection_disconnected(request):
        logger.debug("客户端已断开连接")
        raise EndOfStream("客户端已断开连接")


def _determine_response_status_code(exc_status_code: int) -> int:
    """
    根据异常状态码确定响应状态码
    
    业务错误返回200，只有真正的服务器错误才返回500
    但是 401 和 403 需要保持原状态码，以便前端正确处理
    
    Args:
        exc_status_code: 异常状态码
    
    Returns:
        响应状态码
    """
    if exc_status_code == status.HTTP_401_UNAUTHORIZED:
        return status.HTTP_401_UNAUTHORIZED
    elif exc_status_code == status.HTTP_403_FORBIDDEN:
        return status.HTTP_403_FORBIDDEN
    elif exc_status_code in (status.HTTP_500_INTERNAL_SERVER_ERROR, status.HTTP_503_SERVICE_UNAVAILABLE):
        return exc_status_code
    else:
        return status.HTTP_200_OK


def _add_csrf_token_to_response(response: JSONResponse, exc: HTTPException) -> None:
    """
    如果HTTPException中包含了新的CSRF token，添加到响应头
    
    Args:
        response: JSONResponse对象
        exc: HTTPException异常对象
    """
    if hasattr(exc, '_csrf_token') and exc._csrf_token:
        try:
            response.headers["X-CSRF-Token"] = exc._csrf_token
            logger.debug("已在错误响应中添加正确的CSRF token（供前端自动更新）")
        except Exception:
            pass


async def _create_http_exception_response(
        request: Request,
        exc: HTTPException,
        content: dict | str,
        response_status_code: int
) -> JSONResponse:
    """
    创建HTTPException响应，处理连接检查和CSRF token
    
    Args:
        request: 请求对象
        exc: HTTPException异常对象
        content: 响应内容（字典或字符串）
        response_status_code: 响应状态码
    
    Returns:
        JSONResponse对象
    
    Raises:
        EndOfStream: 如果连接已断开
    """
    # 检查连接是否仍然有效
    try:
        _raise_stream_error_if_disconnected(request)
    except Exception:
        pass

    # 记录严重的 HTTPException (500/503) 到审计日志
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        await record_http_exception_log(exc, request, "HTTPException")

    # 尝试返回响应，但如果连接已断开，捕获异常
    try:
        # 再次检查连接状态（在返回响应前）
        _raise_stream_error_if_disconnected(request)

        # 创建响应
        response = JSONResponse(
            status_code=response_status_code,
            content=content,
        )

        # 添加CSRF token（如果存在）
        _add_csrf_token_to_response(response, exc)

        return response
    except Exception as e:
        # 如果是流异常，直接重新抛出
        if _is_stream_error(e):
            logger.debug("连接已断开，无法发送HTTPException响应")
            raise
        # 其他异常，重新抛出
        raise


def _make_json_serializable(obj):
    """
    递归地将对象转换为JSON可序列化的格式
    处理bytes、datetime等不可序列化的类型
    """
    if isinstance(obj, bytes):
        # 将bytes转换为base64编码的字符串
        try:
            # 尝试解码为UTF-8字符串
            return obj.decode('utf-8', errors='replace')
        except (UnicodeDecodeError, AttributeError):
            # 如果无法解码，返回base64编码
            return base64.b64encode(obj).decode('utf-8')
    elif isinstance(obj, dict):
        return {key: _make_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_json_serializable(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        # 处理对象
        return _make_json_serializable(obj.__dict__)
    else:
        # 其他类型直接返回（JSON可以处理的基本类型）
        return obj


def _client_api_validation_hint(path: str, errors: list) -> str | None:
    """客户开放 API 常见校验失败的可读说明。"""
    if "/client_data" not in path and "/client_products" not in path:
        return None
    for err in errors:
        loc = err.get("loc") or ()
        if err.get("type") == "missing" and "req_time" in loc:
            return (
                "缺少必填参数 req_time（10 位 Unix 秒级时间戳，如 int(time.time())）。"
                "签名须按字母序拼接 client_id、data_type、dimension、end_date、req_time、start_date"
                "（仅非空字段）后追加 &key=客户密钥，再 MD5 小写。"
            )
        if err.get("type") == "missing" and "sign" in loc:
            return "缺少必填参数 sign（MD5 签名，须与 req_time 等参数一并参与计算）。"
    if any(err.get("type") == "json_invalid" for err in errors):
        return (
            "请求体不是合法 JSON，请设置 Content-Type: application/json，"
            "并检查 JSON 语法（如逗号、引号、括号是否匹配）。"
        )
    return None


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    处理请求验证错误
    统一返回标准格式，不暴露敏感信息
    业务错误返回200状态码，通过响应体中的code字段表示错误
    """
    # 获取错误信息并转换为JSON可序列化格式
    errors = exc.errors()
    serializable_errors = _make_json_serializable(errors)

    path = request.url.path
    error_detail = _client_api_validation_hint(path, errors) or "请检查请求参数格式"
    if error_detail == "请检查请求参数格式" and errors:
        first_error = errors[0]
        loc = first_error.get("loc", [])
        msg = first_error.get("msg", "")
        if loc:
            field_name = loc[-1]
            error_detail = f"参数 '{field_name}' 错误: {msg}"
        else:
            error_detail = f"参数错误: {msg}"

    logger.warning(f"请求验证失败: {request.url.path} | 错误: {serializable_errors}")
    error_response = create_error_response(
        error_code=ErrorCode.VALIDATION_ERROR,
        message="请求参数验证失败",
        detail=error_detail,
        data={"errors": serializable_errors},
        path=request.url.path
    )
    # 业务错误返回200状态码，通过响应体中的code字段表示错误
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=error_response,
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """
    处理 HTTPException
    统一返回标准格式
    
    设计原则：
    - 如果 detail 已经是标准格式（字典，包含 code 字段），说明是业务错误，返回200状态码
    - 如果 status_code 是 500 或 503，说明是服务器错误，保持原状态码
    - 其他情况（401等特殊状态码除外），业务错误返回200状态码
    
    Args:
        request: 请求对象
        exc: HTTPException 异常对象
    """
    # 首先检查异常上下文是否是流异常（连接已断开）
    # 如果是，直接重新抛出流异常，让 ASGI 服务器处理
    # 注意：不要在这里抛出，而是让异常自然传播，避免被 global_exception_handler 捕获后再次抛出
    if hasattr(exc, '__context__') and exc.__context__:
        context_exc = exc.__context__
        if _is_stream_error(context_exc):
            logger.debug("HTTPException的上下文是流异常，连接已断开，跳过响应创建")
            # 直接重新抛出流异常，让 ASGI 服务器处理
            # 使用 from None 避免创建新的异常链，防止被 global_exception_handler 捕获
            raise context_exc from None

    # 检查连接是否已断开（使用非阻塞方式）
    # 注意：这里不能尝试读取流，只能检查标记
    try:
        if _check_connection_disconnected(request):
            logger.debug("检测到连接已断开，跳过HTTPException响应创建")
            raise EndOfStream("客户端已断开连接")
    except Exception as stream_exc:
        # 如果检测到连接断开，抛出流异常
        if _is_stream_error(stream_exc):
            logger.debug("检测到连接已断开，跳过HTTPException响应创建")
            raise stream_exc
        # 其他异常，忽略（继续处理HTTPException）

    # 如果 detail 已经是标准格式（字典，包含 code 字段），说明是通过 raise_api_exception 抛出的
    # 此时应该使用 exc.status_code（已经在 raise_api_exception 中正确设置）
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        response_status_code = _determine_response_status_code(exc.status_code)
        return await _create_http_exception_response(request, exc, exc.detail, response_status_code)

    # 否则，从 HTTPException 的 detail 中提取错误信息
    # 这种情况通常是直接使用 HTTPException 抛出的（应该避免，应使用 raise_api_exception）
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

    # 根据状态码映射到错误码
    status_to_error_code = {
        status.HTTP_400_BAD_REQUEST: ErrorCode.BAD_REQUEST,
        status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
        status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
        status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
        status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY: ErrorCode.VALIDATION_ERROR,
        status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.TOO_MANY_REQUESTS,
        status.HTTP_500_INTERNAL_SERVER_ERROR: ErrorCode.INTERNAL_ERROR,
        status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
    }

    error_code = status_to_error_code.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

    error_response = create_error_response(
        error_code=error_code,
        message=detail,
        detail=detail,
        path=request.url.path
    )

    # 业务错误返回200，只有真正的服务器错误才返回500
    # 但是 401 和 403 需要保持原状态码，以便前端正确处理
    response_status_code = _determine_response_status_code(exc.status_code)
    return await _create_http_exception_response(request, exc, error_response, response_status_code)


async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理器
    捕获所有未处理的异常（不包括 HTTPException），防止泄露敏感信息
    
    注意：
    - HTTPException 会被上面的处理器处理，不会到达这里
    - 只有真正的程序代码错误（未捕获的异常）才会到达这里，返回500状态码
    - 流关闭异常（EndOfStream, WouldBlock）直接重新抛出，不记录错误
    
    Args:
        request: 请求对象
        exc: 异常对象
    """
    # HTTPException 应该由专门的处理器处理，不应该到达这里
    # 但如果到达这里，说明可能在异常处理过程中连接已断开
    if isinstance(exc, HTTPException):
        # 检查是否是流关闭异常
        if _is_stream_error(exc):
            # 直接重新抛出，让 ASGI 服务器处理
            raise exc

        # 尝试检查连接状态（通过检查异常上下文）
        # 如果异常上下文是流异常，说明连接已断开，直接重新抛出流异常
        # 注意：如果流异常是从 http_exception_handler 传播过来的，应该直接让它继续传播
        # 检查异常链中是否有流异常（包括 __context__ 和 __cause__）
        context_exc = None
        if hasattr(exc, '__context__') and exc.__context__:
            if _is_stream_error(exc.__context__):
                context_exc = exc.__context__
        if not context_exc and hasattr(exc, '__cause__') and exc.__cause__:
            if _is_stream_error(exc.__cause__):
                context_exc = exc.__cause__

        if context_exc:
            logger.debug("检测到连接断开上下文，跳过HTTPException处理")
            # 直接重新抛出流异常，让 ASGI 服务器处理
            # 使用 from None 避免创建新的异常链，防止被再次捕获
            raise context_exc from None

        # 检查连接是否已断开（使用非阻塞方式）
        # 注意：这里不能尝试读取流，只能检查标记
        try:
            if _check_connection_disconnected(request):
                logger.debug("检测到连接已断开，跳过HTTPException处理")
                raise EndOfStream("客户端已断开连接")
        except Exception as stream_exc:
            # 如果检测到连接断开，抛出流异常
            if _is_stream_error(stream_exc):
                logger.debug("检测到连接已断开，跳过HTTPException处理")
                raise stream_exc
            # 其他异常，忽略（继续处理HTTPException）

        # 如果连接仍然有效，重新抛出 HTTPException 让专门的处理器处理
        # HTTPException 应该由 http_exception_handler 处理，不应该到达这里
        # 如果到达这里，可能是异常处理顺序问题，直接重新抛出让上层处理
        raise exc

    # 检查是否是流关闭相关的异常（客户端提前关闭连接）
    if _is_stream_error(exc):
        # 流关闭异常是正常的（客户端提前关闭连接），不需要记录错误
        # 直接重新抛出，让 ASGI 服务器处理
        raise exc

    # 记录详细的错误信息（包括堆栈跟踪）
    # 注意：RequestLoggingMiddleware 已经记录了简要异常信息，这里记录完整堆栈跟踪
    error_message = str(exc)
    error_type = type(exc).__name__
    try:
        client_ip = get_client_ip(request)
    except Exception:
        client_ip = "unknown"
    
    logger.error(
        f"未处理的异常: {request.method} {request.url.path} | 错误类型: {error_type} | 错误: {error_message} | IP: {client_ip}",
        exc_info=True
    )

    # 记录运行错误到审计日志（异步执行，不阻塞错误响应）
    try:
        # 异步记录错误日志，不阻塞错误响应
        async def record_error_log():
            """将未处理异常异步写入 UserAuditLog，尽量解析当前登录用户。"""
            audit_db = None
            try:
                audit_db = AsyncSessionLocal()

                # 尝试从请求中获取当前用户（如果有认证信息）
                current_user = None
                username = None
                try:

                    token = request.headers.get("Authorization", "").replace("Bearer ", "")
                    if token:
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
                    # 如果无法获取用户，继续使用 None
                    pass

                # 限制错误信息长度
                truncated_error = (
                    error_message[:MAX_ERROR_MESSAGE_LENGTH]
                    if len(error_message) > MAX_ERROR_MESSAGE_LENGTH
                    else error_message
                )

                # 获取堆栈跟踪（限制长度）
                stack_trace = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                truncated_stack = (
                    stack_trace[:MAX_STACK_TRACE_LENGTH]
                    if len(stack_trace) > MAX_STACK_TRACE_LENGTH
                    else stack_trace
                )

                # 收集详细的请求信息
                request_details = {
                    "path": request.url.path,
                    "method": request.method,
                    "stack_trace": truncated_stack,
                    "query_params": str(request.query_params) if request.query_params else None,
                    "client_ip": None,
                    "user_agent": request.headers.get("User-Agent", None)
                }

                # 获取客户端IP
                try:
                    request_details["client_ip"] = get_client_ip(request)
                except Exception:
                    pass

                await log_runtime_error(
                    db=audit_db,
                    error_type=error_type,
                    error_message=truncated_error,
                    request=request,
                    user=current_user,
                    username=username,
                    resource_type="SYSTEM",
                    resource_name=request.url.path,
                    details=request_details
                )
                await audit_db.commit()
            except Exception as log_error:
                # 日志记录失败不应该影响错误处理
                logger.warning(f"记录运行错误日志失败: {log_error}")
            finally:
                if audit_db:
                    try:
                        await audit_db.close()
                    except Exception:
                        pass

        # 在后台任务中记录日志，不阻塞错误响应
        asyncio.create_task(record_error_log())
    except Exception as e:
        # 如果导入或记录日志失败，不影响错误处理
        logger.warning(f"记录运行错误日志时发生异常: {e}", exc_info=True)

    # 生产环境不返回详细错误信息，避免泄露敏感信息
    error_detail = "服务器内部错误，请稍后重试"
    if not settings.is_production:
        # 开发环境可以返回详细错误信息，便于调试
        error_detail = f"服务器内部错误: {str(exc)}"

    error_response = create_error_response(
        error_code=ErrorCode.INTERNAL_ERROR,
        message=error_detail,
        detail=error_detail,
        path=request.url.path
    )

    # 这是真正的程序代码错误，返回500状态码
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response,
    )

async def invalid_filter_parameter_handler(request: Request, exc: InvalidFilterParameterError):
    """筛选参数（逗号分隔整数）格式无效时返回校验错误，避免 500。"""
    logger.warning("筛选参数无效: %s | path=%s", exc, request.url.path)
    error_response = create_error_response(
        error_code=ErrorCode.VALIDATION_ERROR,
        message="请求参数验证失败",
        detail=str(exc),
        path=request.url.path,
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=error_response)


def register_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 实例注册全局异常处理器。"""
    app.exception_handler(RequestValidationError)(validation_exception_handler)
    app.exception_handler(InvalidFilterParameterError)(invalid_filter_parameter_handler)
    app.exception_handler(HTTPException)(http_exception_handler)
    app.exception_handler(Exception)(global_exception_handler)
