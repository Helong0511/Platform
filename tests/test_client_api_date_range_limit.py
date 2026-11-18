"""客户开放 API 日期跨度上限回归测试。"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api_v1.external import client_api


class _BackgroundTasks:
    def add_task(self, *args, **kwargs):
        self.calls = getattr(self, "calls", [])
        self.calls.append((args, kwargs))


@pytest.mark.asyncio
async def test_client_data_rejects_more_than_90_inclusive_days(monkeypatch):
    async def verify(*args, **kwargs):
        return SimpleNamespace(id=17, user_id=7, company_name="isolated")

    monkeypatch.setattr(client_api, "verify_client_request", verify)
    monkeypatch.setattr(client_api, "get_client_ip", lambda request: "192.0.2.10")

    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/client_data"),
        headers={"user-agent": "isolated-test"},
    )
    payload = client_api.ClientDataRequest(
        client_id=17,
        req_time=int(datetime.now(timezone.utc).timestamp()),
        sign="isolated-signature",
        start_date="2026-01-01",
        end_date="2026-04-01",
    )

    with pytest.raises(HTTPException) as caught:
        await client_api.get_client_data(
            request=request,
            background_tasks=_BackgroundTasks(),
            api_request=payload,
            db=SimpleNamespace(),
        )

    # raise_api_exception 使用项目统一错误包装，HTTP status_code 固定为 200；
    # 应断言业务错误码和结构化 detail，而不是假设标准 HTTP 400。
    assert caught.value.status_code == 200
    assert caught.value.detail["code"] == client_api.ErrorCode.INVALID_PARAMETER
    assert "不能超过 90 天" in caught.value.detail["detail"]


@pytest.mark.asyncio
async def test_client_data_accepts_exactly_90_inclusive_days(monkeypatch):
    async def verify(*args, **kwargs):
        return SimpleNamespace(id=17, user_id=7, company_name="isolated")

    monkeypatch.setattr(client_api, "verify_client_request", verify)
    monkeypatch.setattr(client_api, "get_client_ip", lambda request: "192.0.2.10")

    captured = {}

    async def fetch(self, **kwargs):
        captured.update(kwargs)
        return [], 0

    async def get_names(db, user_id):
        return "isolated-user", "Isolated User"

    monkeypatch.setattr(client_api.ClientAdDataQuery, "fetch", fetch)
    monkeypatch.setattr(client_api, "_get_client_user_names", get_names)

    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/client_data"),
        headers={"user-agent": "isolated-test"},
    )
    payload = client_api.ClientDataRequest(
        client_id=17,
        req_time=int(datetime.now(timezone.utc).timestamp()),
        sign="isolated-signature",
        start_date="2026-01-01",
        end_date="2026-03-31",
    )
    response = await client_api.get_client_data(
        request=request,
        background_tasks=_BackgroundTasks(),
        api_request=payload,
        db=SimpleNamespace(),
    )

    assert response.total == 0
    assert captured["start_date"].isoformat() == "2026-01-01"
    assert captured["end_date"].isoformat() == "2026-03-31"
