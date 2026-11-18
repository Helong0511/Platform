"""客户开放 API 日期跨度上限回归测试。"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api_v1.external import client_api


class _BackgroundTasks:
    def add_task(self, *args, **kwargs):
        raise AssertionError("超范围请求不得执行后台副作用")


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

    assert caught.value.status_code == 400
    assert "不能超过 90 天" in str(caught.value.detail)


@pytest.mark.asyncio
async def test_client_data_accepts_exactly_90_inclusive_days(monkeypatch):
    async def verify(*args, **kwargs):
        return SimpleNamespace(id=17, user_id=7, company_name="isolated")

    monkeypatch.setattr(client_api, "verify_client_request", verify)
    monkeypatch.setattr(client_api, "get_client_ip", lambda request: "192.0.2.10")

    # 90 天边界应通过日期校验，随后在查询层之前使用专门的 sentinel 中断。
    class _DB:
        async def execute(self, statement):
            raise RuntimeError("DATE_RANGE_ACCEPTED_SENTINEL")

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

    # 该日期段为 90 天（含首尾），只验证不因跨度上限被拒绝。
    # 实际查询可能因 schema/数据库准备而失败，但不得返回日期范围错误。
    with pytest.raises(HTTPException) as caught:
        await client_api.get_client_data(
            request=request,
            background_tasks=_BackgroundTasks(),
            api_request=payload,
            db=_DB(),
        )
    assert "不能超过 90 天" not in str(caught.value.detail)
