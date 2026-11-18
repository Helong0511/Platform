"""客户开放 API 的异常信息脱敏回归测试。"""
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api_v1.external import client_api


@pytest.mark.asyncio
async def test_client_products_does_not_return_or_log_raw_internal_exception(monkeypatch, caplog):
    private_value = "alice@example.invalid click_id=private-click-id"

    async def fail_verification(*args, **kwargs):
        raise RuntimeError(private_value)

    monkeypatch.setattr(client_api, "verify_client_request", fail_verification)
    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/client_products"),
        headers={"user-agent": "isolated-test-agent"},
    )
    background_tasks = SimpleNamespace(
        add_task=lambda *args, **kwargs: None,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as caught:
            await client_api.get_client_products(
                request=request,
                background_tasks=background_tasks,
                api_request=client_api.ClientProductsRequest(
                    client_id=1,
                    req_time=1,
                    sign="isolated-signature",
                ),
                db=object(),
            )

    assert private_value not in str(caught.value.detail)
    assert private_value not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "查询产品列表失败，请稍后重试" in str(caught.value.detail)


@pytest.mark.asyncio
async def test_background_client_api_audit_failure_logs_only_exception_type(
    monkeypatch, caplog
):
    private_value = "bob@example.invalid ip=203.0.113.9"

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    async def fail_audit(*args, **kwargs):
        raise RuntimeError(private_value)

    monkeypatch.setattr(client_api, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(client_api, "log_user_action", fail_audit)

    with caplog.at_level(logging.WARNING):
        await client_api._background_client_api_side_effects(
            action_type="API_ACCESS",
            user_id=1,
            username="ci-client",
            resource_type="PRODUCT",
            resource_id=None,
            resource_name="产品列表",
            ip_address="203.0.113.10",
            user_agent="isolated-test-agent",
            success=True,
            details={"client_id": 1},
            request_method="POST",
            request_path="/client_products",
        )

    assert private_value not in caplog.text
    assert "RuntimeError" in caplog.text
