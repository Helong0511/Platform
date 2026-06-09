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

        # 检查协议（支持代理情况）
        scheme = request.url.scheme
        # 检查 X-Forwarded-Proto 头（反向代理会设置）
        forwarded_proto = request.headers.get("X-Forwarded-Proto", "").lower()

        # 检查是否来自 Cloudflare（通过 CF-Connecting-IP 头部判断）
        # 如果使用 Cloudflare Flexible SSL，允许来自 Cloudflare 的 HTTP 请求
        cf_connecting_ip = request.headers.get("CF-Connecting-IP")
        is_from_cloudflare = cf_connecting_ip is not None

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
