"""Cap API errors must not disclose internal exception details."""
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api_v1.cpl import caps
from app.core import audit_log


@pytest.mark.asyncio
async def test_cap_consistency_api_redacts_internal_exception_details(monkeypatch, caplog):
    secret_detail = "redis://internal-host:6379 password=do-not-disclose"

    class BrokenCapService:
        async def check_cap_consistency(self, *, offer_id, fix):
            raise RuntimeError(secret_detail)

    class FakeDB:
        def __init__(self):
            self.records = []

        def add(self, record):
            self.records.append(record)

    async def fake_get_cap_service(db):
        return BrokenCapService()

    monkeypatch.setattr(caps, "get_cap_service", fake_get_cap_service)
    monkeypatch.setattr(caps, "commit_audit_log", AsyncMock())
    monkeypatch.setattr(audit_log, "get_client_ip", lambda request: "127.0.0.1")

    db = FakeDB()
    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/caps/check-consistency"),
        headers={},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    current_user = SimpleNamespace(id=1, username="admin")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as exc_info:
            await caps.check_cap_consistency_api(
                request=request,
                offer_id=123,
                fix=False,
                db=db,
                current_user=current_user,
            )

    assert exc_info.value.status_code == 500
    assert secret_detail not in str(exc_info.value.detail)
    assert exc_info.value.detail["detail"] == "检查Cap计数一致性失败，请稍后重试或联系系统管理员。"

    # 使用真实审计写入边界，验证持久化只保留异常类型。
    assert len(db.records) == 1
    assert db.records[0].success is False
    assert db.records[0].error_message == "异常类型：RuntimeError"
    assert secret_detail not in db.records[0].error_message

    # 日志不得输出原始异常消息或异常堆栈中的凭据。
    assert "RuntimeError" in caplog.text
    assert secret_detail not in caplog.text



@pytest.mark.asyncio
async def test_cap_audit_logging_failure_does_not_log_raw_exception(monkeypatch, caplog):
    secret_detail = "mysql://audit-user:do-not-disclose@db.internal:3306/platform"

    class BrokenCapService:
        async def check_cap_consistency(self, *, offer_id, fix):
            raise RuntimeError("cap service failed")

    async def fake_get_cap_service(db):
        return BrokenCapService()

    async def fail_audit_write(**_kwargs):
        raise RuntimeError(secret_detail)

    monkeypatch.setattr(caps, "get_cap_service", fake_get_cap_service)
    monkeypatch.setattr(caps, "log_user_action", fail_audit_write)
    monkeypatch.setattr(caps, "commit_audit_log", AsyncMock())

    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/caps/check-consistency"),
        headers={},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    current_user = SimpleNamespace(id=1, username="admin")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as exc_info:
            await caps.check_cap_consistency_api(
                request=request,
                offer_id=123,
                fix=False,
                db=object(),
                current_user=current_user,
            )

    assert exc_info.value.status_code == 500
    assert secret_detail not in caplog.text
    assert "RuntimeError" in caplog.text
