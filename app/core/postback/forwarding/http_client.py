"""
HTTP 客户端

发送 Postback HTTP 请求。发请求前与重定向链上均做 SSRF 校验，避免打到内网/元数据地址。
"""
import asyncio
import logging
from typing import Dict, Any, Optional, Tuple
import httpx

from app.core.ssrf_guard import (
    SSRFForbiddenError,
    resolve_public_ip,
)

logger = logging.getLogger(__name__)


class _PinnedDNSAsyncHTTPTransport(httpx.AsyncBaseTransport):
    """
    DNS 固定传输层：连接前再次解析并校验，然后把 TCP 目标固定为该 IP。

    HTTP Host 与 TLS SNI 仍使用原始域名；禁用 keep-alive，避免不同域名解析到同一 IP
    时错误复用 TLS 连接。每次重定向都会经过该传输层重新解析和校验。
    """

    def __init__(self, delegate: Optional[httpx.AsyncBaseTransport] = None):
        self._delegate = delegate or httpx.AsyncHTTPTransport(
            trust_env=False,
            limits=httpx.Limits(max_keepalive_connections=0),
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        original_url = request.url
        original_sni = request.extensions.get("sni_hostname")
        original_host = original_url.host

        if original_url.scheme not in ("http", "https") or not original_host:
            raise SSRFForbiddenError("仅允许带主机名的 HTTP/HTTPS 出站 URL")

        # 连接前最后一刻只解析一次并固定 IP，避免重复 DNS 查询及校验/连接竞态。
        pinned_ip = await asyncio.to_thread(resolve_public_ip, original_host)
        if original_url.scheme == "https":
            request.extensions["sni_hostname"] = original_host
        request.url = original_url.copy_with(host=pinned_ip)

        try:
            return await self._delegate.handle_async_request(request)
        finally:
            # 让 HTTPX 的响应/重定向仍以原始 URL 为基准，而不是 IP URL。
            request.url = original_url
            if original_sni is None:
                request.extensions.pop("sni_hostname", None)
            else:
                request.extensions["sni_hostname"] = original_sni

    async def aclose(self) -> None:
        await self._delegate.aclose()


class HttpClient:
    """HTTP 客户端"""

    DEFAULT_TIMEOUT = 12
    CONNECT_TIMEOUT = 5

    @staticmethod
    async def send_request(
        url: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, int, str]:
        """
        发送 HTTP 请求。

        Returns:
            tuple: (是否成功，状态码，响应内容)
        """
        normalized_method = (method or "").upper()
        if normalized_method not in {"GET", "POST"}:
            logger.warning("拒绝不支持的 Postback HTTP 方法：%s", method)
            return False, 0, f"Unsupported HTTP method: {method}"

        try:
            async with httpx.AsyncClient(
                transport=_PinnedDNSAsyncHTTPTransport(),
                timeout=httpx.Timeout(
                    HttpClient.DEFAULT_TIMEOUT,
                    connect=HttpClient.CONNECT_TIMEOUT,
                ),
                follow_redirects=True,
                trust_env=False,
            ) as client:

                if normalized_method == "GET":
                    response = await client.get(url, params=params, headers=headers)
                elif normalized_method == "POST":
                    response = await client.post(
                        url,
                        params=params,
                        json=json_data,
                        headers=headers,
                    )
                else:  # 前置白名单校验保证不可达
                    raise AssertionError("未处理的 Postback HTTP 方法")

                success = 200 <= response.status_code < 400
                content = response.text

                logger.info(
                    f"HTTP 请求完成：method={method}, url={url[:100]}, "
                    f"status={response.status_code}, success={success}"
                )

                return success, response.status_code, content

        except httpx.TimeoutException as e:
            logger.error(f"HTTP 请求超时：{url[:100]}, error={str(e)}")
            return False, 0, f"Timeout: {str(e)}"

        except httpx.RequestError as e:
            err = str(e)
            if err.startswith("SSRF blocked:"):
                logger.warning("Postback 重定向/出站被 SSRF 防护拦截：%s", err)
                return False, 0, err
            logger.error(f"HTTP 请求失败：{url[:100]}, error={err}")
            return False, 0, f"Request Error: {err}"

        except SSRFForbiddenError as e:
            logger.warning("Postback SSRFForbiddenError：%s", e.reason)
            return False, 0, f"SSRF blocked: {e.reason}"

        except Exception as e:
            logger.error(f"HTTP 请求异常：{url[:100]}, error={str(e)}", exc_info=True)
            return False, 0, f"Exception: {str(e)}"
