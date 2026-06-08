"""
上游 API HTTP 响应解析辅助（各任务共用）。

定时拉数任务（TQT / Skymobi / yangyangdeyi / Addermobi / Huguang / zhisuo / Pomiad）
均通过本模块的 post_json / get_json 请求上游；对 HTTP 5xx、429 自动重试。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Mapping, Optional, Union

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SuccessCheck = Union[set[Any], Callable[[Dict[str, Any]], bool]]

# 重试间隔（秒）：第 1 次失败后等 2s，第 2 次 5s …
_UPSTREAM_RETRY_DELAYS = (2.0, 5.0, 10.0)


def _httpx_timeout(total: float) -> httpx.Timeout:
    connect = min(float(settings.UPSTREAM_HTTP_CONNECT_TIMEOUT), total)
    return httpx.Timeout(total, connect=connect)


def _default_max_retries() -> int:
    return max(1, int(settings.UPSTREAM_HTTP_MAX_RETRIES))


def _default_timeout() -> float:
    return max(5.0, float(settings.UPSTREAM_HTTP_TIMEOUT))


def _is_retriable_http_status(status_code: int) -> bool:
    """上游瞬时故障（5xx、限流）可重试；4xx 视为请求/凭证问题不重试。"""
    return status_code == 429 or 500 <= status_code < 600


def ensure_http_ok(
    response: httpx.Response,
    *,
    label: str = "API",
    attempts: Optional[int] = None,
) -> None:
    if response.status_code != 200:
        text = (response.text or "")[:500]
        retry_suffix = f"（已重试 {attempts} 次）" if attempts and attempts > 1 else ""
        logger.error(
            "%s HTTP错误: status=%s body=%s%s",
            label,
            response.status_code,
            text,
            retry_suffix,
        )
        raise Exception(
            f"{label} HTTP错误: 状态码={response.status_code}, 响应={text[:100]}{retry_suffix}"
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
    timeout: Optional[float] = None,
    verify: bool = True,
    max_retries: Optional[int] = None,
) -> Dict[str, Any]:
    total_timeout = timeout if timeout is not None else _default_timeout()
    attempts = max_retries if max_retries is not None else _default_max_retries()
    attempts = max(1, attempts)
    last_error: Optional[Exception] = None

    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(
                timeout=_httpx_timeout(total_timeout),
                verify=verify,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
                    headers=headers,
                )
            if response.status_code != 200:
                text = (response.text or "")[:500]
                if _is_retriable_http_status(response.status_code) and attempt < attempts - 1:
                    delay = _UPSTREAM_RETRY_DELAYS[min(attempt, len(_UPSTREAM_RETRY_DELAYS) - 1)]
                    logger.warning(
                        "%s HTTP %s (尝试 %s/%s)，%.0fs 后重试 body=%s",
                        label,
                        response.status_code,
                        attempt + 1,
                        attempts,
                        delay,
                        text[:100],
                    )
                    await asyncio.sleep(delay)
                    continue
                ensure_http_ok(
                    response,
                    label=label,
                    attempts=attempts if _is_retriable_http_status(response.status_code) else None,
                )
            json_data = parse_json_response(response, label=label)
            if attempt > 0:
                logger.info("%s 第 %s 次重试成功", label, attempt + 1)
            else:
                logger.info("%s 响应: %s", label, json_data)
            return json_data
        except httpx.TimeoutException as e:
            last_error = e
            if attempt < attempts - 1:
                delay = _UPSTREAM_RETRY_DELAYS[min(attempt, len(_UPSTREAM_RETRY_DELAYS) - 1)]
                logger.warning(
                    "%s 请求超时 (尝试 %s/%s，限时 %.0fs)，%.0fs 后重试",
                    label,
                    attempt + 1,
                    attempts,
                    total_timeout,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            logger.error("%s 请求超时: 超过 %.0f 秒未响应 (%s 次尝试)", label, total_timeout, attempts)
            raise Exception(
                f"{label} 请求超时: 超过{total_timeout}秒未响应（已重试 {attempts} 次）"
            ) from e
        except httpx.RequestError as e:
            last_error = e
            if attempt < attempts - 1:
                delay = _UPSTREAM_RETRY_DELAYS[min(attempt, len(_UPSTREAM_RETRY_DELAYS) - 1)]
                logger.warning(
                    "%s 网络错误 (尝试 %s/%s): %s，%.0fs 后重试",
                    label,
                    attempt + 1,
                    attempts,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            logger.error("%s 请求错误: %s", label, e)
            raise Exception(f"{label} 请求失败: {e}") from e

    raise Exception(f"{label} 请求失败: {last_error}")


async def post_json(
    url: str,
    *,
    json_body: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    label: str = "API",
    timeout: Optional[float] = None,
    verify: bool = True,
    max_retries: Optional[int] = None,
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
        max_retries=max_retries,
    )


async def get_json(
    url: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    label: str = "API",
    timeout: Optional[float] = None,
    verify: bool = True,
    max_retries: Optional[int] = None,
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
        max_retries=max_retries,
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
