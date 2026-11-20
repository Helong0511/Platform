"""短链接重定向日志和公开错误响应不得泄露敏感数据。"""
import importlib
import logging

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

from app.routes.short_link.handlers import log_redirect_details


def test_redirect_summary_does_not_log_sensitive_urls_or_parameters(caplog):
    sensitive_values = (
        "https://landing.example/path?access_token=secret-token",
        "https://advertiser.example/callback?api_key=secret-api-key",
        "fbclid=private-click-id",
        "secret-click-id",
    )

    with caplog.at_level(logging.DEBUG, logger="app.routes.short_link.handlers"):
        log_redirect_details(
            short_code="abc123",
            click_id="secret-click-id",
            final_offer_id=12,
            final_channel_id=34,
            advertiser_id=56,
            request_params={"access_token": "secret-token", "fbclid": "private-click-id"},
            original_url_before_replace=sensitive_values[0],
            original_url_after_replace=sensitive_values[1],
            final_url=sensitive_values[1],
            request=None,
        )

    output = caplog.text
    for secret in sensitive_values:
        assert secret not in output
    assert "abc123" in output
    assert "offer_id=12" in output
    assert "channel_id=34" in output


@pytest.mark.asyncio
async def test_public_redirect_hides_raw_exception_from_logs_and_response(monkeypatch, caplog):
    route_module = importlib.import_module("app.routes.short_link.router")

    async def raise_sensitive_error(_short_code):
        raise RuntimeError("postgresql://service:database-secret@db.internal/platform")

    monkeypatch.setattr(route_module, "get_short_link_from_cache", raise_sensitive_error)

    request = Request({
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/s/abc123",
        "raw_path": b"/s/abc123",
        "query_string": b"access_token=request-secret",
        "headers": [(b"host", b"example.test")],
        "client": ("127.0.0.1", 12345),
        "server": ("example.test", 443),
    })

    with caplog.at_level(logging.ERROR, logger="app.routes.short_link.router"):
        with pytest.raises(HTTPException) as exc_info:
            await route_module.redirect_short_link_public(
                short_code="abc123",
                offer_id=None,
                channel_id=None,
                request=request,
                background_tasks=BackgroundTasks(),
                db=object(),
            )

    rendered_error = repr(exc_info.value.detail)
    assert "database-secret" not in rendered_error
    assert "db.internal" not in rendered_error
    assert "暂时不可用" in rendered_error
    assert "database-secret" not in caplog.text
    assert "request-secret" not in caplog.text
    assert "RuntimeError" in caplog.text
