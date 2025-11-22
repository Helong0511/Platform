"""
统一的异常处理工具
提供标准化的 HTTPException 创建函数
"""
from fastapi import HTTPException, status
from typing import Optional, Any
from app.core.errors import ErrorCode, get_error_message, create_error_response


def raise_api_exception(
        error_code: int,
        message: Optional[str] = None,
        detail: Optional[str] = None,
        status_code: Optional[int] = None,
        data: Optional[Any] = None
) -> None:
    """
    抛出标准化的 API 异常
    
    设计原则：
    - 业务错误（用户输入错误、资源不存在、权限不足等）返回 200 状态码，通过响应体中的 code 字段表示错误
    - 只有真正的服务器错误（程序异常）才返回 500 状态码
    
    Args:
        error_code: 错误码（使用 ErrorCode 枚举）
        message: 错误信息（如果为 None，会根据 error_code 自动获取）
        detail: 详细错误信息（可选）
        status_code: HTTP 状态码（如果为 None，会根据 error_code 自动映射。业务错误默认200，服务器错误500）
        data: 附加数据（可选）
    
    Raises:
        HTTPException: 标准化的 HTTP 异常
    """
    # 获取错误信息
    error_message = get_error_message(error_code, message)

    # 如果没有提供 detail，使用 message
    if detail is None:
        detail = error_message

    # 如果没有提供 status_code，根据 error_code 映射
    # 业务错误默认返回200，只有真正的服务器错误才返回500
    if status_code is None:
        status_code = _map_error_code_to_status_code(error_code)

    # 创建错误响应
    error_response = create_error_response(
        error_code=error_code,
        message=error_message,
        detail=detail,
        data=data
    )

    # 抛出 HTTPException，FastAPI 会自动处理并返回标准格式
    raise HTTPException(
        status_code=status_code,
        detail=error_response
    )


def _map_error_code_to_status_code(error_code: int) -> int:
    """
    将错误码映射到 HTTP 状态码
    
    设计原则：
    - 业务错误（用户输入错误、资源不存在、权限不足等）返回 200，通过响应体中的 code 字段表示错误
    - 只有真正的服务器错误（程序异常、系统错误）才返回 500
    
    Args:
        error_code: 错误码
    
    Returns:
        HTTP 状态码（业务错误返回200，服务器错误返回500）
    """
    # 只有以下情况返回非200状态码：
    # 1. 认证相关错误（401）- 需要特殊处理，浏览器会自动处理
    # 2. 真正的服务器内部错误（500）- 程序代码错误
    # 3. 服务不可用（503）- 系统级错误

    if error_code == ErrorCode.UNAUTHORIZED:
        # 401 未授权：需要特殊处理，浏览器会自动处理，保持401
        return status.HTTP_401_UNAUTHORIZED
    elif error_code == ErrorCode.INTERNAL_ERROR:
        # 500 服务器内部错误：真正的程序代码错误
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    elif error_code == ErrorCode.SERVICE_UNAVAILABLE:
        # 503 服务不可用：系统级错误
        return status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        # 所有其他业务错误（400, 403, 404, 409, 422, 429等）都返回200
        # 通过响应体中的 code 字段来区分不同的错误类型
        return status.HTTP_200_OK
