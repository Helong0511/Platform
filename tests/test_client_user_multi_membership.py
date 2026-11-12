"""同一客户登录用户关联多个 Client 主体的管理接口回归测试。"""
from types import SimpleNamespace

import pytest

from app.api_v1.clients import clients as clients_api
from app.models.models import UserRole


class _Scalars:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _Result:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return _Scalars(self.value)


class _DB:
    def __init__(self, values):
        self.values = list(values)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.values.pop(0))

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_client_can_be_reassigned_to_user_with_existing_client_membership(monkeypatch):
    client = SimpleNamespace(
        id=101,
        user_id=1,
        key="opaque-test-key",
        company_name="Existing client record",
        is_active=True,
    )
    new_user = SimpleNamespace(id=2)
    db = _DB([client, new_user, client])

    async def no_op(*args, **kwargs):
        return None

    monkeypatch.setattr(clients_api, "log_update", no_op)
    monkeypatch.setattr(clients_api, "commit_audit_log", no_op)
    monkeypatch.setattr(
        clients_api,
        "_client_public_dict",
        lambda value: {"id": value.id, "user_id": value.user_id},
    )

    request = SimpleNamespace()
    update = SimpleNamespace(
        user_id=2,
        model_dump=lambda **kwargs: {"user_id": 2},
    )
    current_user = SimpleNamespace(id=999, username="ci-admin", role=UserRole.ADMIN)

    response = await clients_api.update_client(
        request=request,
        client_id=101,
        client_in=update,
        db=db,
        current_user=current_user,
    )

    assert client.user_id == 2
    assert response.data == {"id": 101, "user_id": 2}
    # 仅需读取目标 Client、新 User 和更新后的 Client；不再执行一对一冲突查询。
    assert len(db.statements) == 3
