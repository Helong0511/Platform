"""
HTTP 客户端

发送 Postback HTTP 请求。发请求前与重定向链上均做 SSRF 校验，避免打到内网/元数据地址。
"""
import logging
from typing import Dict, Any, Optional, Tuple
import httpx

from app.core.ssrf_guard import SSRFForbiddenError, assert_outbound_url_safe, validate_outbound_url

logger = logging.getLogger(__name__)


class HttpClient:
    """HTTP 客户端"""

    DEFAULT_TIMEOUT = 12
    CONNECT_TIMEOUT = 5

    @staticmethod
    async def _ssrf_request_hook(request: httpx.Request) -> None:
        """httpx 请求钩子：含跟随重定向后的每一次请求都会触发。"""
        try:
            assert_outbound_url_safe(str(request.url))
        except SSRFForbiddenError as exc:
            raise httpx.RequestError(
                f"SSRF blocked: {exc.reason}",
                request=request,
            ) from exc

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
        try:
            assert_outbound_url_safe(url)
        except SSRFForbiddenError as exc:
            logger.warning(
                "Postback 出站被 SSRF 防护拦截：url=%s reason=%s",
                url[:100],
                exc.reason,
            )
            return False, 0, f"SSRF blocked: {exc.reason}"

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    HttpClient.DEFAULT_TIMEOUT,
                    connect=HttpClient.CONNECT_TIMEOUT,
                ),
                follow_redirects=True,
                event_hooks={"request": [HttpClient._ssrf_request_hook]},
            ) as client:

                if method.upper() == "GET":
                    response = await client.get(url, params=params, headers=headers)
                elif method.upper() == "POST":
                    response = await client.post(
                        url,
                        params=params,
                        json=json_data,
                        headers=headers,
                    )
                else:
                    logger.warning(f"不支持的 HTTP 方法：{method}，使用 GET")
                    response = await client.get(url, params=params, headers=headers)

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
