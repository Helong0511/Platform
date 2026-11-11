"""Postback 回调请求体/Query 参数解析。"""
import json
import logging
from typing import Any, Dict

from fastapi import Request

logger = logging.getLogger(__name__)


async def collect_postback_raw_data(request: Request) -> Dict[str, Any]:
    """
    从 GET Query 与 POST Body 收集 Postback 原始参数（Body 同名键覆盖 Query）。
    """
    raw_data: Dict[str, Any] = {}
    for key, value in request.query_params.items():
        raw_data[key] = value

    if request.method != "POST":
        return raw_data

    content_type = request.headers.get("content-type", "").lower()
    try:
        if "application/json" in content_type or not content_type:
            try:
                body_data = await request.json()
                if isinstance(body_data, dict):
                    raw_data.update(body_data)
            except (json.JSONDecodeError, ValueError, Exception):
                pass
        elif (
            "application/x-www-form-urlencoded" in content_type
            or "multipart/form-data" in content_type
        ):
            try:
                form_data = await request.form()
                for key, value in form_data.items():
                    raw_data[key] = value
            except Exception:
                pass
        else:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    body_str = body_bytes.decode("utf-8")
                    if "=" in body_str:
                        for pair in body_str.split("&"):
                            if "=" in pair:
                                key, value = pair.split("=", 1)
                                raw_data[key] = value
            except Exception:
                pass
    except Exception as e:
        logger.warning("读取 POST Body 数据时发生错误：%s", type(e).__name__)

    return raw_data
