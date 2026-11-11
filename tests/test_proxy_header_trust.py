"""反向代理信任边界测试：客户端不能伪造 Cloudflare IP 头影响应用 IP 识别。"""
from pathlib import Path
from types import SimpleNamespace

from starlette.requests import Request

from app.core import utils


def _request(peer_ip: str, headers: dict[str, str]) -> Request:
    raw_headers = [(b"host", b"platform.example.invalid")]
    raw_headers.extend(
        (key.lower().encode("ascii"), value.encode("latin-1"))
        for key, value in headers.items()
    )
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/health",
            "raw_path": b"/api/v1/health",
            "query_string": b"",
            "headers": raw_headers,
            "client": (peer_ip, 54321),
            "server": ("127.0.0.1", 443),
        }
    )


def test_untrusted_peer_cannot_spoof_client_ip_headers(monkeypatch):
    from app.core import config

    monkeypatch.setattr(
        config,
        "settings",
        SimpleNamespace(
            TRUST_PROXY_HEADERS=True,
            get_trusted_proxy_ips=lambda: ["127.0.0.1", "::1"],
        ),
    )

    request = _request(
        "198.51.100.23",
        {
            "CF-Connecting-IP": "203.0.113.99",
            "X-Forwarded-For": "203.0.113.88",
            "X-Real-IP": "203.0.113.77",
        },
    )

    assert utils.get_client_ip(request) == "198.51.100.23"


def test_nginx_overwrites_cf_connecting_ip_with_realip_resolved_remote_addr():
    root = Path(__file__).resolve().parents[1]
    nginx_config = (
        root / "nginx" / "btfrx.online" / "nginx.conf"
    ).read_text(encoding="utf-8")
    cloudflare_config = (
        root / "nginx" / "btfrx.online" / "cloudflare_real_ip.conf"
    ).read_text(encoding="utf-8")

    assert "include /data/Platform/nginx/btfrx.online/cloudflare_real_ip.conf;" in nginx_config
    assert "proxy_set_header CF-Connecting-IP $remote_addr;" in nginx_config
    assert "proxy_set_header CF-Connecting-IP $http_cf_connecting_ip;" not in nginx_config
    assert "real_ip_header CF-Connecting-IP;" in cloudflare_config
    assert "set_real_ip_from 173.245.48.0/20;" in cloudflare_config
    assert "set_real_ip_from 2400:cb00::/32;" in cloudflare_config
