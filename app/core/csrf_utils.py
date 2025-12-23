"""
CSRF工具函数
提供安全的HTTPException抛出机制，避免在连接断开时抛出异常
"""
import logging
from fastapi import HTTPException, status, Request
from typing import Optional

logger = logging.getLogger(__name__)


def safe_raise_csrf_exception(
    request: Request,
    detail: str,
    status_code: int = status.HTTP_403_FORBIDDEN
) -> None:
    """
    安全地抛出CSRF相关的HTTPException
    
    在抛出异常之前检查连接状态，如果连接已断开，不抛出异常
    使用特殊的异常类型，让调用者知道连接已断开
    
    Args:
        request: FastAPI请求对象
        detail: 错误详情
        status_code: HTTP状态码（默认403）
        
    Raises:
        HTTPException: 如果连接仍然有效
        RuntimeError: 如果连接已断开（包含 "Connection disconnected" 消息）
        EndOfStream: 如果连接已断开（直接抛出流异常）
    """
    # 检查连接是否仍然有效
    # 方法1: 检查 _is_disconnected 属性
    try:
        if hasattr(request, '_is_disconnected') and request._is_disconnected:
            logger.debug("客户端已断开连接，跳过CSRF异常抛出")
            from anyio import EndOfStream
            raise EndOfStream("客户端已断开连接")
    except Exception as e:
        # 如果已经是 EndOfStream，直接重新抛出
        error_type = type(e).__name__
        error_module = type(e).__module__
        if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
            "anyio" in error_module):
            raise
        # 如果是 RuntimeError 且包含 "Connection disconnected"，转换为 EndOfStream
        if isinstance(e, RuntimeError) and "Connection disconnected" in str(e):
            from anyio import EndOfStream
            raise EndOfStream("客户端已断开连接")
    
    # 方法2: 检查 scope 中是否有连接断开标记
    try:
        if hasattr(request, 'scope') and isinstance(request.scope, dict):
            if request.scope.get('_disconnected', False):
                logger.debug("从 scope 检测到连接已断开，跳过CSRF异常抛出")
                from anyio import EndOfStream
                raise EndOfStream("客户端已断开连接")
    except Exception as e:
        # 如果已经是 EndOfStream，直接重新抛出
        error_type = type(e).__name__
        error_module = type(e).__module__
        if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
            "anyio" in error_module):
            raise
    
    # 方法3: 尝试检查请求流是否仍然有效
    # 注意：我们不能实际接收数据，因为这会消耗请求体
    try:
        # 检查请求的 receive 函数是否存在（表示连接可能仍然有效）
        if hasattr(request, '_receive'):
            # 请求流存在，连接可能仍然有效
            pass
    except (ConnectionError, OSError, RuntimeError) as stream_error:
        # 如果检查过程中发现流已关闭，抛出连接断开异常
        error_type_name = type(stream_error).__name__
        error_module = type(stream_error).__module__
        if ("EndOfStream" in error_type_name or "WouldBlock" in error_type_name or 
            "anyio" in error_module):
            logger.debug("检测到流已关闭，跳过CSRF异常抛出")
            # 直接重新抛出原始的流异常，而不是创建新的
            raise stream_error
        # 其他连接错误，重新抛出
        raise
    except Exception:
        # 其他异常，继续执行
        pass
    
    # 只有在连接仍然有效时才抛出异常
    raise HTTPException(status_code=status_code, detail=detail)

