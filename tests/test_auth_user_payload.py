"""登录 user 载荷构建单测"""
from types import SimpleNamespace

from app.core.auth_user_payload import build_auth_user_payload
from app.models.models import UserRole


def test_build_auth_user_payload_includes_client_key_for_client():
    user = SimpleNamespace(
        id=10,
        username="client_a",
        full_name="客户A",
        email="a@example.com",
        role=UserRole.CLIENT,
    )
    client = SimpleNamespace(
        id=5,
        key="secret-uuid-key",
        company_name="测试公司",
        api_enabled=True,
        password_change_enabled=False,
    )
    payload = build_auth_user_payload(
        user,
        api_enabled=True,
        has_publisher=False,
        client=client,
    )
    assert payload["api_enabled"] is True
    assert payload["client"]["id"] == 5
    assert payload["client"]["key"] == "secret-uuid-key"


def test_build_auth_user_payload_admin_has_no_client():
    user = SimpleNamespace(
        id=1,
        username="admin",
        full_name="Admin",
        email="admin@example.com",
        role=UserRole.ADMIN,
    )
    payload = build_auth_user_payload(user)
    assert "client" not in payload
