"""
HTTPS强制中间件
生产环境强制使用HTTPS，防止中间人攻击和网络劫持
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    HTTPS强制重定向中间件
    生产环境将所有HTTP请求重定向到HTTPS
    """

    def __init__(self, app: ASGIApp):
        """
        Args:
            app: 下游 ASGI 应用（FastAPI 实例）
        """
        super().__init__(app)
        self.app = app

    async def dispatch(self, request: Request, call_next):
        """
        生产环境将 HTTP 请求重定向或拒绝为 HTTPS，并为响应附加 HSTS 头。

        Args:
            request: 当前 HTTP 请求
            call_next: 调用链中的下一个处理器

        Returns:
            RedirectResponse（GET 非 HTTPS）、JSONResponse（非 GET）或下游响应
        """
        # ---------- 非生产环境直接放行 ----------
        if not settings.is_production:
            return await call_next(request)

        # 只有直连对端属于显式配置的可信代理时，才允许读取代理协议/Cloudflare 头。
        # 不能仅凭客户端可伪造的 X-Forwarded-Proto / CF-Connecting-IP 绕过 HTTPS。
        scheme = request.url.scheme
        peer_ip = request.client.host if request.client else ""
        trusted_proxy_ips = set(settings.get_trusted_proxy_ips())
        trusted_proxy = bool(
            settings.TRUST_PROXY_HEADERS
            and peer_ip
            and peer_ip in trusted_proxy_ips
        )
        forwarded_proto = (
            request.headers.get("X-Forwarded-Proto", "").strip().lower()
            if trusted_proxy else ""
        )
        # Cloudflare Flexible SSL 兼容仅在可信反向代理链路上生效；
        # Nginx 必须按 cloudflare_real_ip.conf 仅信任 Cloudflare 官方源站网段。
        cf_connecting_ip = (
            request.headers.get("CF-Connecting-IP", "").strip()
            if trusted_proxy else ""
        )
        is_from_cloudflare = bool(cf_connecting_ip)

        # 特殊路径豁免：/bridge/ 路由（桥页静态资源）允许 HTTP
        # 因为这是内部代理请求，Nginx 会处理 SSL
        path = request.url.path
        is_bridge_static = path.startswith("/bridge/")

        # 如果协议不是 HTTPS，且不是来自 Cloudflare，且不是豁免路径，重定向到 HTTPS
        # 如果来自 Cloudflare（即使使用 Flexible SSL），允许 HTTP 请求通过
        if scheme != "https" and forwarded_proto != "https" and not is_from_cloudflare and not is_bridge_static:
            # 构建HTTPS URL
            https_url = request.url.replace(scheme="https")

            # 对于GET请求，使用301永久重定向
            # 对于其他请求，返回错误提示
            if request.method == "GET":
                logger.warning(
                    f"HTTP请求被重定向到HTTPS: {request.url.path} | "
                    f"IP: {request.client.host if request.client else 'unknown'}"
                )
                return RedirectResponse(
                    url=str(https_url),
                    status_code=301,  # 永久重定向
                    headers={
                        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload"
                    }
                )
            else:
                # 非GET请求不支持重定向，返回错误
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "detail": "生产环境必须使用HTTPS连接"
                    },
                    headers={
                        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload"
                    }
                )

        # 继续处理请求
        response = await call_next(request)

        # 确保响应头包含HSTS
        if "Strict-Transport-Security" not in response.headers:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        return response
