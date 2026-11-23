"""删除审计必须与最终业务结果处于同一事务。"""
from types import SimpleNamespace

import pytest

from app.api_v1.users import users as users_api
from app.api_v1.products import products as products_api


@pytest.mark.asyncio
async def test_user_delete_audit_is_written_only_after_service_delete(monkeypatch):
    events = []
    target = SimpleNamespace(
        id=20,
        username="target-user",
        role="client",
        email="target@example.invalid",
    )

    class FakeUserService:
        async def get_user_by_id(self, *_args, **_kwargs):
            events.append("load")
            return target

        async def delete_user(self, *_args, **_kwargs):
            events.append("delete")

    async def get_service(_db):
        return FakeUserService()

    async def log_delete(**_kwargs):
        events.append("audit")

    async def commit(_db):
        events.append("commit")

    monkeypatch.setattr(users_api, "get_user_service", get_service)
    monkeypatch.setattr(users_api, "log_delete", log_delete)
    monkeypatch.setattr(users_api, "commit_audit_log", commit)

    response = await users_api.delete_user(
        request=SimpleNamespace(),
        user_id=target.id,
        db=object(),
        current_user=SimpleNamespace(id=1, username="admin"),
    )

    assert events == ["load", "delete", "audit", "commit"]
    assert response is not None


@pytest.mark.asyncio
async def test_user_delete_failure_does_not_write_success_audit(monkeypatch):
    events = []

    class FakeUserService:
        async def get_user_by_id(self, *_args, **_kwargs):
            return SimpleNamespace(
                id=20, username="linked-user", role="client", email=None
            )

        async def delete_user(self, *_args, **_kwargs):
            events.append("delete")
            raise RuntimeError("linked clients prevent deletion")

    async def get_service(_db):
        return FakeUserService()

    async def log_delete(**_kwargs):
        events.append("audit")

    async def commit(_db):
        events.append("commit")

    monkeypatch.setattr(users_api, "get_user_service", get_service)
    monkeypatch.setattr(users_api, "log_delete", log_delete)
    monkeypatch.setattr(users_api, "commit_audit_log", commit)

    with pytest.raises(RuntimeError, match="prevent deletion"):
        await users_api.delete_user(
            request=SimpleNamespace(),
            user_id=20,
            db=object(),
            current_user=SimpleNamespace(id=1, username="admin"),
        )

    assert events == ["delete"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "expected_audit"),
    [
        (
            {
                "transferred": False,
                "message": "产品已成功删除",
                "ad_data_count": 0,
            },
            "delete_audit",
        ),
        (
            {
                "transferred": True,
                "message": "产品已转移到临时挂靠",
                "new_client_id": 99,
                "ad_data_count": 3,
            },
            "update_audit",
        ),
    ],
)
async def test_product_audit_matches_completed_delete_or_transfer(
    monkeypatch, outcome, expected_audit
):
    events = []
    product = SimpleNamespace(id=30, name="test-product", client_id=7)

    class FakeProductService:
        async def get_product_by_id(self, *_args, **_kwargs):
            events.append("load")
            return product

        async def delete_product(self, *_args, **_kwargs):
            events.append("mutate")
            return outcome

    async def get_service(_db):
        return FakeProductService()

    async def log_delete(**_kwargs):
        events.append("delete_audit")

    async def log_update(**_kwargs):
        events.append("update_audit")

    async def commit(_db):
        events.append("commit")

    monkeypatch.setattr(products_api, "get_product_service", get_service)
    monkeypatch.setattr(products_api, "log_delete", log_delete)
    monkeypatch.setattr(products_api, "log_update", log_update)
    monkeypatch.setattr(products_api, "commit_audit_log", commit)

    response = await products_api.delete_product(
        request=SimpleNamespace(),
        product_id=product.id,
        db=object(),
        current_user=SimpleNamespace(id=1, username="admin"),
    )

    assert events == ["load", "mutate", expected_audit, "commit"]
    assert response is not None


@pytest.mark.asyncio
async def test_product_mutation_failure_does_not_write_success_audit(monkeypatch):
    events = []
    product = SimpleNamespace(id=30, name="test-product", client_id=7)

    class FakeProductService:
        async def get_product_by_id(self, *_args, **_kwargs):
            return product

        async def delete_product(self, *_args, **_kwargs):
            events.append("mutate")
            raise RuntimeError("concurrent ad data prevents deletion")

    async def get_service(_db):
        return FakeProductService()

    async def log_delete(**_kwargs):
        events.append("audit")

    async def log_update(**_kwargs):
        events.append("audit")

    async def commit(_db):
        events.append("commit")

    monkeypatch.setattr(products_api, "get_product_service", get_service)
    monkeypatch.setattr(products_api, "log_delete", log_delete)
    monkeypatch.setattr(products_api, "log_update", log_update)
    monkeypatch.setattr(products_api, "commit_audit_log", commit)

    with pytest.raises(RuntimeError, match="prevents deletion"):
        await products_api.delete_product(
            request=SimpleNamespace(),
            product_id=product.id,
            db=object(),
            current_user=SimpleNamespace(id=1, username="admin"),
        )

    assert events == ["mutate"]
