"""客户 API 密钥脱敏与创建一次性返回测试。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api_v1.clients.clients import _client_create_dict, _client_public_dict


def _fake_client(*, key: str | None = "uuid-key", user_full_name: str | None = "测试用户"):
    user = SimpleNamespace(full_name=user_full_name) if user_full_name else None
    return SimpleNamespace(
        id=1,
        key=key,
        company_name="测试公司",
        contact_person=None,
        phone=None,
        address=None,
        allowed_ips=None,
        is_active=True,
        api_enabled=False,
        password_change_enabled=True,
        user_id=10,
        created_at=None,
        updated_at=None,
        user=user,
    )


def test_client_public_dict_masks_key():
    data = _client_public_dict(_fake_client())
    assert "key" not in data
    assert data["has_api_key"] is True
    assert data["user_full_name"] == "测试用户"


def test_client_create_dict_returns_key_once():
    data = _client_create_dict(_fake_client(key="create-only-key"))
    assert data["key"] == "create-only-key"
    assert data["has_api_key"] is True


def test_client_public_dict_without_key():
    data = _client_public_dict(_fake_client(key=None))
    assert data["has_api_key"] is False
