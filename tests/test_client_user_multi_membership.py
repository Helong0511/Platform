"""同一客户登录用户关联多个 Client 主体的管理接口回归测试。"""
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import mysql

from app.api_v1.clients import clients as clients_api
from app.models.models import Publisher, UserRole
from app.services.cpl.publisher_service import PublisherService


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



class _PublisherResult:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return self

    def all(self):
        return self.value

    def first(self):
        return self.value

    def scalar(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class _PublisherDB:
    def __init__(self, responses):
        self.responses = list(responses)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _PublisherResult(self.responses.pop(0))


def _compiled_sql(statement):
    return str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_publisher_detail_accepts_any_active_client_membership():
    publisher = Publisher(
        id=501,
        client_id=202,
        publisher_name="synthetic-publisher",
        email="private@example.invalid",
        postback_url="https://internal.invalid/postback",
        postback_success_check="success",
        price_discount=2.5,
    )
    user = SimpleNamespace(id=77, role=UserRole.CLIENT)
    db = _PublisherDB([publisher, [101, 202]])

    result = await PublisherService(db).get_publisher_by_id(
        publisher_id=501,
        current_user=user,
        include_client=False,
    )

    assert result is publisher
    assert result.email is None
    assert result.postback_url is None
    assert result.price_discount == 0.0
    client_scope_sql = _compiled_sql(db.statements[1])
    assert "clients.user_id = 77" in client_scope_sql
    assert "clients.is_active IS true" in client_scope_sql


@pytest.mark.asyncio
async def test_publisher_list_scopes_all_active_client_memberships():
    publisher = Publisher(
        id=501,
        client_id=202,
        publisher_name="synthetic-publisher",
        email="private@example.invalid",
        postback_url="https://internal.invalid/postback",
        postback_success_check="success",
        price_discount=2.5,
    )
    user = SimpleNamespace(id=77, role=UserRole.CLIENT)
    db = _PublisherDB([[101, 202], 1, [publisher]])

    publishers, total = await PublisherService(db).get_publishers(
        current_user=user,
        page=1,
        page_size=20,
    )

    assert publishers == [publisher]
    assert total == 1
    assert publisher.email is None
    assert "publishers.client_id IN (101, 202)" in _compiled_sql(db.statements[1])
    assert "publishers.client_id IN (101, 202)" in _compiled_sql(db.statements[2])
