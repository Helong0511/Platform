"""
HTTP 客户端

发送 Postback HTTP 请求。发请求前与重定向链上均做 SSRF 校验，避免打到内网/元数据地址。
"""
import logging
from typing import Dict, Any, Optional, Tuple
import httpx

from app.core.ssrf_guard import validate_outbound_url

logger = logging.getLogger(__name__)


class HttpClient:
    """HTTP 客户端"""

    # HTTP 超时配置（秒）：下游不可达时尽快失败，避免拖垮入库/补发接口
    DEFAULT_TIMEOUT = 12
    CONNECT_TIMEOUT = 5

    @staticmethod
    async def _ssrf_request_hook(request: httpx.Request) -> None:
        """
        httpx 请求钩子：含跟随重定向后的每一次请求都会触发。
        校验失败时抛出 RequestError，由 send_request 统一捕获。
        """
        ok, reason = validate_outbound_url(str(request.url))
        if not ok:
            raise httpx.RequestError(
                f"SSRF blocked: {reason}",
                request=request,
            )

    @staticmethod
    async def send_request(
        url: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, int, str]:
        """
        发送 HTTP 请求

        Args:
            url: 请求 URL
            method: 请求方法（GET/POST）
            params: 查询参数
            json_data: JSON 数据（用于 POST）
            headers: 请求头

        Returns:
            tuple: (是否成功，状态码，响应内容)
        """
        # 首跳预先校验，避免无效 URL 浪费连接；重定向由 event_hooks 再检
        ok, reason = validate_outbound_url(url)
        if not ok:
            logger.warning("Postback 出站被 SSRF 防护拦截：url=%s reason=%s", url[:100], reason)
            return False, 0, f"SSRF blocked: {reason}"

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

        except Exception as e:
            logger.error(f"HTTP 请求异常：{url[:100]}, error={str(e)}", exc_info=True)
            return False, 0, f"Exception: {str(e)}"
