"""HTTPS 代理头信任边界测试：客户端不能伪造代理头跳过 HTTPS 强制。"""
import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.core import https_middleware


def _request(*, peer_ip: str, path: str = "/api/private", headers=None):
    raw_headers = [(b"host", b"platform.example.invalid")]
    for name, value in (headers or {}).items():
        raw_headers.append((name.lower().encode("ascii"), value.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": raw_headers,
            "client": (peer_ip, 54321),
            "server": ("127.0.0.1", 80),
        }
    )


@pytest.mark.asyncio
async def test_untrusted_client_cannot_spoof_forwarded_proto_or_cloudflare_header(monkeypatch):
    monkeypatch.setattr(https_middleware.settings, "is_production", True)
    monkeypatch.setattr(https_middleware.settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(
        https_middleware.settings,
        "get_trusted_proxy_ips",
        lambda: ["127.0.0.1", "::1"],
    )
    middleware = https_middleware.HTTPSRedirectMiddleware(lambda scope, receive, send: None)
    called = False

    async def call_next(_request):
        nonlocal called
        called = True
        return Response("passed")

    response = await middleware.dispatch(
        _request(
            peer_ip="198.51.100.23",
            headers={
                "X-Forwarded-Proto": "https",
                "CF-Connecting-IP": "198.51.100.23",
            },
        ),
        call_next,
    )

    assert response.status_code == 301
    assert response.headers["location"].startswith("https://")
    assert called is False


@pytest.mark.asyncio
async def test_configured_local_reverse_proxy_may_forward_https_scheme(monkeypatch):
    monkeypatch.setattr(https_middleware.settings, "is_production", True)
    monkeypatch.setattr(https_middleware.settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(
        https_middleware.settings,
        "get_trusted_proxy_ips",
        lambda: ["127.0.0.1", "::1"],
    )
    middleware = https_middleware.HTTPSRedirectMiddleware(lambda scope, receive, send: None)

    async def call_next(_request):
        return Response("passed")

    response = await middleware.dispatch(
        _request(
            peer_ip="127.0.0.1",
            headers={"X-Forwarded-Proto": "https"},
        ),
        call_next,
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_cloudflare_client_ip_header_alone_never_proves_https(monkeypatch):
    monkeypatch.setattr(https_middleware.settings, "is_production", True)
    monkeypatch.setattr(https_middleware.settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(
        https_middleware.settings,
        "get_trusted_proxy_ips",
        lambda: ["127.0.0.1"],
    )
    middleware = https_middleware.HTTPSRedirectMiddleware(lambda scope, receive, send: None)

    async def call_next(_request):
        return Response("passed")

    trusted_proxy_response = await middleware.dispatch(
        _request(
            peer_ip="127.0.0.1",
            headers={"CF-Connecting-IP": "203.0.113.9"},
        ),
        call_next,
    )
    untrusted_peer_response = await middleware.dispatch(
        _request(
            peer_ip="203.0.113.9",
            headers={"CF-Connecting-IP": "203.0.113.9"},
        ),
        call_next,
    )

    assert trusted_proxy_response.status_code == 301
    assert untrusted_peer_response.status_code == 301


@pytest.mark.asyncio
async def test_disabling_proxy_header_trust_disables_all_header_exceptions(monkeypatch):
    monkeypatch.setattr(https_middleware.settings, "is_production", True)
    monkeypatch.setattr(https_middleware.settings, "TRUST_PROXY_HEADERS", False)
    monkeypatch.setattr(
        https_middleware.settings,
        "get_trusted_proxy_ips",
        lambda: ["127.0.0.1"],
    )
    middleware = https_middleware.HTTPSRedirectMiddleware(lambda scope, receive, send: None)

    async def call_next(_request):
        return Response("passed")

    response = await middleware.dispatch(
        _request(
            peer_ip="127.0.0.1",
            headers={
                "X-Forwarded-Proto": "https",
                "CF-Connecting-IP": "203.0.113.9",
            },
        ),
        call_next,
    )

    assert response.status_code == 301
