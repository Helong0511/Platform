"""同一用户关联多个 Client 时，客户级策略必须一致生效。"""
from types import SimpleNamespace

import pytest

from app.models.models import UserRole
from app.services import user_service as user_service_module
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_password_change_denied_if_any_linked_client_disables_it(monkeypatch):
    user = SimpleNamespace(
        id=909,
        role=UserRole.CLIENT,
        clients=[
            SimpleNamespace(password_change_enabled=True),
            SimpleNamespace(password_change_enabled=False),
        ],
    )
    service = UserService(db=SimpleNamespace())

    async def get_user_by_id(user_id, current_user, include_client=False):
        assert user_id == user.id
        assert current_user is user
        assert include_client is True
        return user

    def deny(*args, **kwargs):
        raise PermissionError(kwargs.get("detail", "denied"))

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(user_service_module, "raise_api_exception", deny)

    with pytest.raises(PermissionError, match="至少一个关联客户已禁用密码修改"):
        await service.change_password(
            user_id=user.id,
            old_password="synthetic-old-password",
            new_password="synthetic-new-password",
            current_user=user,
        )
