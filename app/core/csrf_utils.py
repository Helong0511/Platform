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
        ConnectionDisconnected: 如果连接已断开（自定义异常，让调用者处理）
    """
    # 检查连接是否仍然有效
    try:
        if hasattr(request, '_is_disconnected') and request._is_disconnected:
            logger.debug("客户端已断开连接，跳过CSRF异常抛出")
            # 抛出特殊的异常，让调用者知道连接已断开
            # 使用RuntimeError，这样调用者可以捕获并处理
            raise RuntimeError("Connection disconnected")
    except RuntimeError as e:
        if "Connection disconnected" in str(e):
            # 重新抛出，让调用者处理
            raise
    except Exception:
        pass
    
    # 只有在连接仍然有效时才抛出异常
    raise HTTPException(status_code=status_code, detail=detail)

