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
    """
    # 检查连接是否仍然有效
    # 方法1: 检查 _is_disconnected 属性
    try:
        if hasattr(request, '_is_disconnected') and request._is_disconnected:
            logger.debug("客户端已断开连接，跳过CSRF异常抛出")
            raise RuntimeError("Connection disconnected")
    except RuntimeError as e:
        if "Connection disconnected" in str(e):
            raise
    except Exception:
        pass
    
    # 方法2: 尝试检查请求流是否仍然有效
    # 如果连接已断开，尝试访问请求体可能会触发异常
    # 注意：我们不能实际接收数据，因为这会消耗请求体
    # 所以我们只能检查属性，不能实际调用 receive
    try:
        # 检查请求的 receive 函数是否存在（表示连接可能仍然有效）
        if hasattr(request, '_receive'):
            # 请求流存在，连接可能仍然有效
            pass
        # 检查 scope 中是否有连接信息
        if hasattr(request, 'scope'):
            # 如果 scope 中存在连接信息，检查是否已断开
            scope = request.scope
            if isinstance(scope, dict):
                # 检查是否有连接断开标记
                if scope.get('_disconnected', False):
                    logger.debug("从 scope 检测到连接已断开，跳过CSRF异常抛出")
                    raise RuntimeError("Connection disconnected")
    except RuntimeError as e:
        if "Connection disconnected" in str(e):
            raise
    except (ConnectionError, OSError, RuntimeError) as stream_error:
        # 如果检查过程中发现流已关闭，抛出连接断开异常
        error_type_name = type(stream_error).__name__
        error_module = type(stream_error).__module__
        if ("EndOfStream" in error_type_name or "WouldBlock" in error_type_name or 
            "anyio" in error_module):
            logger.debug("检测到流已关闭，跳过CSRF异常抛出")
            raise RuntimeError("Connection disconnected")
        # 其他连接错误，重新抛出
        raise
    except Exception:
        # 其他异常，继续执行
        pass
    
    # 只有在连接仍然有效时才抛出异常
    raise HTTPException(status_code=status_code, detail=detail)

