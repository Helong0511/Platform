"""Postback HTTP client must reject unknown methods instead of silently sending GET."""
import pytest

from app.core.postback.forwarding.http_client import HttpClient


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH", "TRACE", "", "getx"])
async def test_unsupported_method_is_rejected_without_creating_http_client(monkeypatch, method):
    def unexpected_client(*args, **kwargs):
        raise AssertionError("HTTP client must not be created for unsupported methods")

    monkeypatch.setattr(
        "app.core.postback.forwarding.http_client.httpx.AsyncClient",
        unexpected_client,
    )

    success, status_code, message = await HttpClient.send_request(
        url="https://example.invalid/callback",
        method=method,
    )

    assert success is False
    assert status_code == 0
    assert message.startswith("Unsupported HTTP method:")

