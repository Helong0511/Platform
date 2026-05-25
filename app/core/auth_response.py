"""
认证相关响应与异常辅助（与业务 API 的 ResponseBaseSchema 对齐）
"""
from typing import Any, Dict, Optional

from fastapi import status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.schemas.base import ResponseBaseSchema


def raise_auth_error(
        error_code: int,
        detail: str,
        *,
        http_status: int = status.HTTP_401_UNAUTHORIZED,
) -> None:
    """抛出认证类错误（保留真实 HTTP 状态码，响应体为标准 JSON）"""
    raise_api_exception(error_code, detail=detail, status_code=http_status)


def build_token_json_response(
        access_token: str,
        refresh_token: Optional[str],
        user: Dict[str, Any],
        *,
        message: str = "登录成功",
) -> JSONResponse:
    """
    构建登录/刷新成功响应：{ code: 200, message, data: LoginResponse 字段 }
    同时设置 HttpOnly access_token Cookie
    """
    token_payload = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user,
    }
    body = ResponseBaseSchema.success(data=token_payload, message=message).model_dump()
    response = JSONResponse(content=body)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return response
