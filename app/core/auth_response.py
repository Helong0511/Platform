"""
认证 Cookie 与登录/刷新响应辅助。

令牌仅通过 HttpOnly Cookie 下发，JSON 响应体不包含 access_token / refresh_token。
"""
from typing import Any, Dict, Optional

from fastapi import Response, status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.schemas.base import ResponseBaseSchema

# 与 Nginx 同域反代一致；set/delete 必须使用相同 path
AUTH_COOKIE_PATH = "/"


def clear_auth_cookies(response: Response) -> None:
    """清除认证 Cookie（logout / refresh 失败时调用）。"""
    for key in ("access_token", "refresh_token"):
        response.delete_cookie(
            key=key,
            path=AUTH_COOKIE_PATH,
            httponly=True,
            secure=settings.is_production,
            samesite="lax",
        )


def apply_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: Optional[str] = None,
) -> None:
    """设置 access_token / refresh_token HttpOnly Cookie。"""
    response.set_cookie(
        key="access_token",
        value=access_token,
        path=AUTH_COOKIE_PATH,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            path=AUTH_COOKIE_PATH,
            httponly=True,
            secure=settings.is_production,
            samesite="lax",
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        )


def raise_auth_error(
    error_code: int,
    detail: str,
    *,
    http_status: int = status.HTTP_401_UNAUTHORIZED,
) -> None:
    """抛出认证类 HTTP 异常（标准 JSON 响应体）。"""
    raise_api_exception(error_code, detail=detail, status_code=http_status)


def auth_failure_response(exc: StarletteHTTPException) -> JSONResponse:
    """认证失败响应：保留 HTTP 状态与业务 JSON，并清除无效 Cookie。"""
    content = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
    response = JSONResponse(status_code=exc.status_code, content=content)
    clear_auth_cookies(response)
    return response


def mark_auth_failure_cookies(exc: StarletteHTTPException) -> StarletteHTTPException:
    """
    标记 HTTPException：全局异常处理器将清除认证 Cookie。

    用于 refresh 等须 raise（避免 get_db 误提交）且须清 Cookie 的场景。
    """
    exc._clear_auth_cookies = True  # type: ignore[attr-defined]
    return exc


def raise_auth_failure(exc: StarletteHTTPException) -> None:
    """抛出须清除 Cookie 的认证失败异常（供全局处理器统一响应）。"""
    raise mark_auth_failure_cookies(exc)


def build_token_json_response(
    access_token: str,
    refresh_token: Optional[str],
    user: Dict[str, Any],
    *,
    message: str = "登录成功",
) -> JSONResponse:
    """
    登录/刷新成功：响应体仅含 user + token_type，令牌写入 HttpOnly Cookie。
    """
    token_payload = {
        "token_type": "bearer",
        "user": user,
    }
    body = ResponseBaseSchema.success(data=token_payload, message=message).model_dump()
    response = JSONResponse(content=body)
    apply_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
    return response
