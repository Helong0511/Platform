"""
上游 API HTTP 响应解析辅助（各任务共用）。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Mapping, Optional, Union

import httpx

logger = logging.getLogger(__name__)

SuccessCheck = Union[set[Any], Callable[[Dict[str, Any]], bool]]


def ensure_http_ok(response: httpx.Response, *, label: str = "API") -> None:
    if response.status_code != 200:
        text = (response.text or "")[:500]
        logger.error("%s HTTP错误: status=%s body=%s", label, response.status_code, text)
        raise Exception(
            f"{label} HTTP错误: 状态码={response.status_code}, 响应={text[:100]}"
        )


def parse_json_response(response: httpx.Response, *, label: str = "API") -> Dict[str, Any]:
    try:
        data = response.json()
    except Exception as e:
        text = (response.text or "")[:500]
        logger.error("%s JSON解析失败: %s body=%s", label, e, text)
        raise Exception(f"{label} 响应格式错误: 无法解析JSON") from e
    if not data:
        text = (response.text or "")[:500]
        raise Exception(f"{label} 返回空响应: {text[:100]}")
    return data


async def _request_json(
    method: str,
    url: str,
    *,
    json_body: Optional[Mapping[str, Any]] = None,
    params: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    label: str = "API",
    timeout: float = 20.0,
    verify: bool = True,
) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=verify) as client:
            response = await client.request(
                method,
                url,
                json=json_body,
                params=params,
                headers=headers,
            )
    except httpx.TimeoutException as e:
        logger.error("%s 请求超时: %s", label, e)
        raise Exception(f"{label} 请求超时: 超过{timeout}秒未响应") from e
    except httpx.RequestError as e:
        logger.error("%s 请求错误: %s", label, e)
        raise Exception(f"{label} 请求失败: {e}") from e

    ensure_http_ok(response, label=label)
    json_data = parse_json_response(response, label=label)
    logger.info("%s 响应: %s", label, json_data)
    return json_data


async def post_json(
    url: str,
    *,
    json_body: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    label: str = "API",
    timeout: float = 20.0,
    verify: bool = True,
) -> Dict[str, Any]:
    """POST 请求并返回解析后的 JSON。"""
    return await _request_json(
        "POST",
        url,
        json_body=json_body,
        headers=headers,
        label=label,
        timeout=timeout,
        verify=verify,
    )


async def get_json(
    url: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    label: str = "API",
    timeout: float = 20.0,
    verify: bool = True,
) -> Dict[str, Any]:
    """GET 请求并返回解析后的 JSON。"""
    return await _request_json(
        "GET",
        url,
        params=params,
        headers=headers,
        label=label,
        timeout=timeout,
        verify=verify,
    )


def api_error_message(
    json_data: Dict[str, Any],
    *,
    code_keys: tuple[str, ...] = ("code", "ret", "status", "state"),
    msg_keys: tuple[str, ...] = ("msg", "message"),
) -> Optional[str]:
    code = None
    for k in code_keys:
        if k in json_data:
            code = json_data.get(k)
            break
    msg = None
    for k in msg_keys:
        if json_data.get(k):
            msg = json_data.get(k)
            break
    if code is None and msg is None:
        return None
    parts = []
    if code is not None:
        parts.append(f"{code_keys[0] if code_keys else 'code'}={code}")
    if msg:
        parts.append(f"msg={msg}")
    return ", ".join(parts)


def raise_unless_api_success(
    json_data: Dict[str, Any],
    success: SuccessCheck,
    *,
    label: str = "API",
    code_key: str = "code",
) -> None:
    """业务状态不成功时抛异常。"""
    ok = success(json_data) if callable(success) else json_data.get(code_key) in success
    if ok:
        return
    detail = api_error_message(json_data) or "未知错误"
    logger.error("%s 业务错误: %s", label, detail)
    raise Exception(f"{label} 错误: {detail}")
