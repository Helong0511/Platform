"""Postback 回调请求体/Query 参数解析。"""
import json
from typing import Any, Dict
from urllib.parse import parse_qsl

from fastapi import Request

MAX_POSTBACK_BODY_BYTES = 64 * 1024
MAX_POSTBACK_FIELDS = 200


class PostbackPayloadTooLarge(ValueError):
    """Postback 请求超过解析上限。"""


class UnsupportedPostbackContentType(ValueError):
    """Postback 不支持的请求体类型。"""


async def collect_postback_raw_data(request: Request) -> Dict[str, Any]:
    """有界解析 GET Query 与 POST JSON/Form，拒绝无界或不支持的请求体。

    S2S 回调不需要上传文件；明确拒绝 multipart/file，避免公开入口被用作文件上传点。
    """
    raw_data: Dict[str, Any] = {}
    query_string = request.scope.get("query_string", b"")
    if len(query_string) > MAX_POSTBACK_BODY_BYTES:
        raise PostbackPayloadTooLarge("query string exceeds limit")
    if len(request.query_params) > MAX_POSTBACK_FIELDS:
        raise PostbackPayloadTooLarge("too many query parameters")
    for key, value in request.query_params.items():
        raw_data[key] = value

    if request.method != "POST":
        return raw_data

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_POSTBACK_BODY_BYTES:
                raise PostbackPayloadTooLarge("request body exceeds limit")
        except ValueError as exc:
            if isinstance(exc, PostbackPayloadTooLarge):
                raise
            raise ValueError("invalid Content-Length") from exc

    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in {
        "",
        "application/json",
        "application/x-www-form-urlencoded",
    }:
        raise UnsupportedPostbackContentType("unsupported Postback content type")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_POSTBACK_BODY_BYTES:
            raise PostbackPayloadTooLarge("request body exceeds limit")
        body.extend(chunk)

    if not body:
        return raw_data

    if content_type in {"", "application/json"}:
        try:
            body_data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON Postback body") from exc
        if not isinstance(body_data, dict):
            raise ValueError("Postback JSON body must be an object")
        if len(body_data) > MAX_POSTBACK_FIELDS:
            raise PostbackPayloadTooLarge("too many Postback fields")
        raw_data.update(body_data)
    else:
        try:
            form_items = parse_qsl(
                body.decode("utf-8"),
                keep_blank_values=True,
                strict_parsing=False,
                max_num_fields=MAX_POSTBACK_FIELDS,
                encoding="utf-8",
                errors="strict",
            )
        except ValueError as exc:
            if "Max number of fields" in str(exc):
                raise PostbackPayloadTooLarge("too many Postback fields") from exc
            raise ValueError("invalid URL-encoded Postback body") from exc
        for key, value in form_items:
            raw_data[key] = value

    if len(raw_data) > MAX_POSTBACK_FIELDS:
        raise PostbackPayloadTooLarge("too many combined Postback fields")
    return raw_data
