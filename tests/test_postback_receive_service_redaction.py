"""公开 Postback 接收入口不得向上游或日志泄露内部异常/PII。"""
import logging

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.services.cpl import postback_receive_service as receive_module


def _request():
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/postback/demo",
            "raw_path": b"/api/v1/postback/demo",
            "query_string": b"",
            "headers": [(b"host", b"platform.example.invalid")],
            "client": ("198.51.100.20", 54321),
            "server": ("127.0.0.1", 443),
        }
    )


@pytest.mark.asyncio
async def test_receive_failure_does_not_log_raw_exception_or_pii(monkeypatch, caplog):
    sensitive_error = (
        "downstream failed for buyer@example.invalid "
        "click_id=private-click ip=203.0.113.20"
    )

    async def parsed_data(request):
        return {"email": "buyer@example.invalid", "click_id": "private-click"}

    async def process(**kwargs):
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(receive_module, "collect_postback_raw_data", parsed_data)
    monkeypatch.setattr(receive_module, "get_client_ip", lambda request: "203.0.113.20")
    monkeypatch.setattr(receive_module.PostbackProcessor, "process", process)

    caplog.set_level(logging.ERROR)
    with pytest.raises(HTTPException) as exc:
        await receive_module.postback_receive_service.receive_postback(
            _request(), "demo", object()
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == receive_module._POSTBACK_RETRY_HINT
    assert "RuntimeError" in caplog.text
    assert "buyer@example.invalid" not in caplog.text
    assert "private-click" not in caplog.text
    assert "203.0.113.20" not in caplog.text
    assert sensitive_error not in caplog.text


def test_retryable_result_message_is_not_exposed_to_upstream():
    with pytest.raises(HTTPException) as exc:
        receive_module.raise_if_postback_retryable(
            {
                "success": False,
                "retryable": True,
                "message": "SQL error includes buyer@example.invalid and private-click",
            }
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == receive_module._POSTBACK_RETRY_HINT
    assert "buyer@example.invalid" not in exc.value.detail
    assert "private-click" not in exc.value.detail
