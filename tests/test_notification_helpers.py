"""
通知 helpers 单元测试（无数据库依赖）。
"""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.errors import ErrorCode
from app.models.models import UserRole
from app.services.notification.helpers import (
    assert_client_config_access,
    assert_conversion_resend_access,
)


def _client_user(client_id=5):
    user = MagicMock()
    user.role = UserRole.CLIENT
    user.client_id = client_id
    return user


def test_assert_client_config_access_denied():
    with pytest.raises(HTTPException) as exc_info:
        assert_client_config_access(_client_user(client_id=1), client_id=99)
    assert exc_info.value.detail["code"] == ErrorCode.ACCESS_DENIED


def test_assert_conversion_resend_access_admin_ok():
    user = MagicMock()
    user.role = UserRole.ADMIN
    conversion = MagicMock(client_id=99)
    assert_conversion_resend_access(user, conversion)
