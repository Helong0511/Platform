"""Cap API errors must not disclose internal exception details."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api_v1.cpl import caps


@pytest.mark.asyncio
async def test_cap_consistency_api_redacts_internal_exception_details(monkeypatch):
    secret_detail = "redis://internal-host:6379 password=do-not-disclose"

    class BrokenCapService:
        async def check_cap_consistency(self, *, offer_id, fix):
            raise RuntimeError(secret_detail)

    async def fake_get_cap_service(db):
        return BrokenCapService()

    monkeypatch.setattr(caps, "get_cap_service", fake_get_cap_service)
    monkeypatch.setattr(caps, "log_user_action", AsyncMock())
    monkeypatch.setattr(caps, "commit_audit_log", AsyncMock())

    with pytest.raises(HTTPException) as exc_info:
        await caps.check_cap_consistency_api(
            request=SimpleNamespace(),
            offer_id=123,
            fix=False,
            db=object(),
            current_user=SimpleNamespace(id=1),
        )

    assert exc_info.value.status_code == 500
    assert secret_detail not in str(exc_info.value.detail)
    assert exc_info.value.detail == "检查Cap计数一致性失败，请稍后重试或联系系统管理员。"
    caps.log_user_action.assert_awaited_once()
    assert caps.log_user_action.await_args.kwargs["error_message"] == secret_detail
