"""Postback 公开请求解析大小与编码边界测试。"""
import pytest
from starlette.requests import Request

from app.core.postback.request_parser import (
    MAX_POSTBACK_BODY_BYTES,
    PostbackPayloadTooLarge,
    UnsupportedPostbackContentType,
    collect_postback_raw_data,
)


def _request(method, body=b"", content_type="application/json", query=b""):
    consumed = False

    async def receive():
        nonlocal consumed
        if consumed:
            return {"type": "http.disconnect"}
        consumed = True
        return {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }

    headers = []
    if content_type:
        headers.append((b"content-type", content_type.encode("ascii")))
    if method == "POST":
        headers.append((b"content-length", str(len(body)).encode("ascii")))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": "/postback/test",
        "raw_path": b"/postback/test",
        "query_string": query,
        "headers": headers,
        "client": ("203.0.113.10", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope, receive)


@pytest.mark.asyncio
async def test_json_postback_body_is_parsed():
    request = _request("POST", b'{"conversion_id":"c1","payout":"1.25"}')
    assert await collect_postback_raw_data(request) == {
        "conversion_id": "c1",
        "payout": "1.25",
    }


@pytest.mark.asyncio
async def test_urlencoded_postback_body_is_parsed():
    request = _request(
        "POST",
        b"conversion_id=c1&payout=1.25",
        "application/x-www-form-urlencoded",
    )
    assert await collect_postback_raw_data(request) == {
        "conversion_id": "c1",
        "payout": "1.25",
    }


@pytest.mark.asyncio
async def test_oversized_postback_body_is_rejected():
    request = _request(
        "POST",
        b"x" * (MAX_POSTBACK_BODY_BYTES + 1),
        "application/json",
    )
    with pytest.raises(PostbackPayloadTooLarge):
        await collect_postback_raw_data(request)


@pytest.mark.asyncio
async def test_multipart_file_upload_is_not_accepted():
    request = _request("POST", b"ignored", "multipart/form-data; boundary=abc")
    with pytest.raises(UnsupportedPostbackContentType):
        await collect_postback_raw_data(request)


@pytest.mark.asyncio
async def test_invalid_json_is_rejected():
    request = _request("POST", b"{invalid", "application/json")
    with pytest.raises(ValueError):
        await collect_postback_raw_data(request)


@pytest.mark.asyncio
async def test_query_string_is_bounded():
    request = _request("GET", query=b"x=" + b"a" * MAX_POSTBACK_BODY_BYTES)
    with pytest.raises(PostbackPayloadTooLarge):
        await collect_postback_raw_data(request)
