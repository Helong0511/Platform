"""出站 SSRF 防护与 DNS 固定连接回归测试；全程不发起真实网络请求。"""
from __future__ import annotations

import socket

import httpx
import pytest

from app.core import ssrf_guard
from app.core.postback.forwarding import http_client


def _addr_info(address: str, family: int = socket.AF_INET):
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 0))


def test_resolve_public_ip_accepts_public_address(monkeypatch):
    monkeypatch.setattr(
        ssrf_guard.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [_addr_info("8.8.8.8")],
    )

    assert ssrf_guard.resolve_public_ip("example.test") == "8.8.8.8"


def test_resolve_public_ip_rejects_mixed_public_and_private_dns(monkeypatch):
    monkeypatch.setattr(
        ssrf_guard.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            _addr_info("8.8.8.8"),
            _addr_info("127.0.0.1"),
        ],
    )

    with pytest.raises(ssrf_guard.SSRFForbiddenError, match="禁网段"):
        ssrf_guard.resolve_public_ip("mixed.example.test")


def test_resolve_public_ip_rejects_ipv4_mapped_private_ipv6():
    with pytest.raises(ssrf_guard.SSRFForbiddenError):
        ssrf_guard.resolve_public_ip("::ffff:127.0.0.1")


def test_dns_rebinding_is_rechecked_at_transport_connection(monkeypatch):
    answers = iter([
        [_addr_info("8.8.8.8")],       # 发送前的 URL 检查
        [_addr_info("169.254.169.254")],  # 实际建立连接前的再次解析
    ])

    monkeypatch.setattr(
        ssrf_guard.socket,
        "getaddrinfo",
        lambda *args, **kwargs: next(answers),
    )

    ok, reason = ssrf_guard.validate_outbound_url("https://rebind.example.test/path")
    assert ok is True
    assert reason == ""

    with pytest.raises(ssrf_guard.SSRFForbiddenError, match="禁网段"):
        ssrf_guard.resolve_public_ip("rebind.example.test")


@pytest.mark.asyncio
async def test_pinned_transport_preserves_host_and_tls_sni(monkeypatch):
    monkeypatch.setattr(
        http_client,
        "resolve_public_ip",
        lambda hostname: "8.8.8.8",
    )

    class CaptureTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.connected_host = None
            self.host_header = None
            self.sni_hostname = None

        async def handle_async_request(self, request):
            self.connected_host = request.url.host
            self.host_header = request.headers.get("host")
            self.sni_hostname = request.extensions.get("sni_hostname")
            return httpx.Response(200, request=request)

        async def aclose(self):
            return None

    delegate = CaptureTransport()
    transport = http_client._PinnedDNSAsyncHTTPTransport(delegate=delegate)
    request = httpx.Request("GET", "https://example.test/callback")
    original_url = request.url

    response = await transport.handle_async_request(request)

    assert response.status_code == 200
    assert delegate.connected_host == "8.8.8.8"
    assert delegate.host_header == "example.test"
    assert delegate.sni_hostname == "example.test"
    assert request.url == original_url
    assert "sni_hostname" not in request.extensions
