"""API 异常与认证错误体格式单测"""
import pytest
from fastapi import HTTPException

from app.core.errors import ErrorCode, create_error_response
from app.core.exceptions import raise_api_exception


def test_raise_api_exception_has_standard_detail():
    with pytest.raises(HTTPException) as exc_info:
        raise_api_exception(ErrorCode.NOT_FOUND, detail="资源不存在")
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == ErrorCode.NOT_FOUND
    assert "资源不存在" in (detail.get("detail") or detail.get("message", ""))


def test_create_error_response_fields():
    body = create_error_response(
        error_code=ErrorCode.FORBIDDEN,
        message="禁止",
        detail="无权限",
    )
    assert body["code"] == ErrorCode.FORBIDDEN
    assert body["message"] == "禁止"
    assert body["detail"] == "无权限"


def test_security_raise_auth_helper():
    from app.core.security import _raise_auth

    with pytest.raises(HTTPException) as exc_info:
        _raise_auth("登录已过期", error_code=ErrorCode.TOKEN_EXPIRED)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == ErrorCode.TOKEN_EXPIRED
