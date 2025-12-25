"""
安全中间件模块
提供API限流、安全响应头、请求日志、响应压缩等功能
"""
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message
import time
import logging
import gzip
from io import BytesIO
# 类型注解已迁移到内置类型（Python 3.10+）
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional
from app.core.config import settings
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# ====== API限流存储 ======
# 使用内存存储限流信息（Redis不可用时使用）
_rate_limit_store: dict[str, dict[str, tuple[int, datetime]]] = defaultdict(dict)

# ====== 限流配置 ======
# 从配置中读取限流设置，提供默认值
DEFAULT_RATE_LIMIT = getattr(settings, 'API_RATE_LIMIT', 100)
DEFAULT_RATE_WINDOW = 60  # 秒

# 登录接口限流：从配置中读取，防止暴力破解
LOGIN_RATE_LIMIT = getattr(settings, 'LOGIN_RATE_LIMIT', 5)
LOGIN_RATE_WINDOW = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    API限流中间件
    防止API滥用和暴力破解攻击
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.app = app

    async def dispatch(self, request: Request, call_next):
        logger.info(f"RateLimitMiddleware处理请求: {request.method} {request.url.path}")
        
        # ====== 排除短链接路由（不限流） ======
        # 短链接访问需要高并发支持，不能限流
        path = request.url.path
        is_short_link = (
            path.startswith("/s/") or  # /s/{short_code} 路由
            path.startswith("/api/v1/short-links/")  # /api/v1/short-links/{short_code} 路由
        )
        
        if is_short_link:
            logger.debug(f"短链接路由跳过限流: {path}")
            response = await call_next(request)
            return response
        
        # ====== 获取客户端标识 ======
        # 使用IP地址作为限流标识（生产环境可结合用户ID）
        try:
            from app.core.utils import get_client_ip
            client_ip = get_client_ip(request)
            logger.info(f"获取到客户端IP: {client_ip}")
        except Exception as e:
            logger.warning(f"获取客户端IP失败: {e}，使用默认IP 'testclient'")
            client_ip = "testclient"

        # ====== 检查是否为登录接口 ======
        # 登录接口使用更严格的限流策略（防止暴力破解）
        is_login = request.url.path.endswith("/login") and request.method == "POST"
        logger.info(f"是否为登录接口: {is_login}")
        logger.info(f"路径: {request.url.path}")
        logger.info(f"方法: {request.method}")
        limit = LOGIN_RATE_LIMIT if is_login else DEFAULT_RATE_LIMIT
        window = LOGIN_RATE_WINDOW if is_login else DEFAULT_RATE_WINDOW
        logger.info(f"限流配置: 限制={limit}/{window}秒")

        # ====== 生产环境：对敏感接口增加额外限流 ======
        if settings.is_production:
            sensitive_paths = ["/api/v1/auth/login", "/api/v1/users", "/api/v1/clients"]
            if any(path in request.url.path for path in sensitive_paths):
                # 敏感接口使用更严格的限流
                limit = min(limit, 30)  # 最多30次/分钟

        # ====== 尝试使用Redis进行限流 ======
        redis_client = await get_redis_client()
        now = datetime.now(timezone.utc)
        current_window_key = f"{int(now.timestamp() / window)}"
        rate_limit_key = f"rate_limit:{client_ip}:{current_window_key}"
        
        if redis_client:
            # 使用Redis进行限流（支持多进程）
            try:
                # 获取当前计数
                current_count = await redis_client.get(rate_limit_key)
                current_count = int(current_count) if current_count else 0
                
                # 检查是否超过限制
                if current_count >= limit:
                    logger.warning(f"API限流触发（Redis）: IP={client_ip}, 路径={request.url.path}, 限制={limit}/{window}秒")
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "detail": "请求过于频繁，请稍后再试"
                        },
                        headers={
                            "Retry-After": str(window),
                            "X-RateLimit-Limit": str(limit),
                            "X-RateLimit-Remaining": "0",
                        }
                    )
                
                # 增加计数并设置过期时间
                await redis_client.incr(rate_limit_key)
                await redis_client.expire(rate_limit_key, window)
                
                # 继续处理请求
                response = await call_next(request)
                
                # 获取更新后的计数
                updated_count = await redis_client.get(rate_limit_key)
                updated_count = int(updated_count) if updated_count else current_count + 1
                
                # 添加限流响应头
                remaining = max(0, limit - updated_count)
                response.headers["X-RateLimit-Limit"] = str(limit)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Reset"] = str(int((now + timedelta(seconds=window)).timestamp()))
                
                return response
            except Exception as e:
                error_msg = str(e) or repr(e) or "未知错误"
                error_type = type(e).__name__
                logger.warning(f"Redis限流操作失败: {error_type} - {error_msg}，回退到内存存储")
                # Redis操作失败，回退到内存存储
        
        # ====== 使用内存存储进行限流（Redis不可用时） ======
        client_requests = _rate_limit_store[client_ip]

        # 清理过期记录
        expired_keys = [
            key for key, (count, timestamp) in client_requests.items()
            if (now - timestamp).total_seconds() > window
        ]
        for key in expired_keys:
            del client_requests[key]

        # 统计当前窗口的请求数
        current_count, _ = client_requests.get(current_window_key, (0, now))

        # ====== 检查是否超过限制 ======
        if current_count >= limit:
            logger.warning(f"API限流触发（内存）: IP={client_ip}, 路径={request.url.path}, 限制={limit}/{window}秒")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "请求过于频繁，请稍后再试"
                },
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                }
            )

        # ====== 更新请求计数 ======
        client_requests[current_window_key] = (current_count + 1, now)

        # ====== 继续处理请求 ======
        response = await call_next(request)

        # ====== 添加限流响应头 ======
        remaining = max(0, limit - current_count - 1)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int((now + timedelta(seconds=window)).timestamp()))

        return response


class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """
    性能监控中间件
    记录慢请求和查询性能
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.app = app
        self.slow_request_threshold = 1.0  # 慢请求阈值（秒）
    
    async def dispatch(self, request: Request, call_next):
        from app.core.utils import get_client_ip
        
        start_time = time.time()
        
        # 处理请求
        response = await call_next(request)
        
        # 计算处理时间
        process_time = time.time() - start_time
        
        # 记录慢请求
        if process_time > self.slow_request_threshold:
            try:
                client_ip = get_client_ip(request)
            except Exception as e:
                logger.warning(f"获取客户端IP失败: {e}，使用默认IP 'testclient'")
                client_ip = "testclient"
            logger.warning(
                f"慢请求: {request.method} {request.url.path} "
                f"耗时 {process_time:.2f}s, IP: {client_ip}"
            )
        
        # 添加性能头
        response.headers["X-Process-Time"] = str(round(process_time, 3))
        
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    安全响应头中间件
    添加安全相关的HTTP响应头，防止XSS、点击劫持等攻击
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.app = app

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # ====== 安全响应头（防止网络劫持和XSS攻击） ======
        # X-Content-Type-Options: 防止MIME类型嗅探
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 注意：X-Frame-Options 和 X-XSS-Protection 已过时
        # 使用 Content-Security-Policy 的 frame-ancestors 替代 X-Frame-Options
        # 现代浏览器已内置 XSS 保护，X-XSS-Protection 已不再需要

        # Referrer-Policy: 控制referrer信息，防止信息泄露
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Cache-Control: API 响应不应该被缓存
        # 注意：对于静态资源，应该由 nginx 设置缓存策略
        # 使用 no-store 即可，无需 must-revalidate（no-store 已经足够禁止缓存）
        if not response.headers.get("Cache-Control"):
            response.headers["Cache-Control"] = "no-store"

        # Permissions-Policy: 限制浏览器功能，防止恶意使用
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )

        # Content-Security-Policy: 内容安全策略（严格模式，防止XSS和网络劫持）
        # 注意：CSP主要用于HTML页面，API响应（JSON）不需要CSP头
        # 只对HTML响应设置CSP，避免在API响应中添加不必要的头
        content_type = response.headers.get("Content-Type", "").lower()
        is_html_response = "text/html" in content_type or request.url.path.endswith(".html")
        
        if is_html_response:
            # 生产环境使用更严格的CSP，禁止内联脚本和eval
            if settings.is_production:
                # 生产环境：严格CSP，禁止unsafe-inline和unsafe-eval
                csp = (
                    "default-src 'self'; "
                    "script-src 'self'; "  # 生产环境禁止unsafe-inline和unsafe-eval
                    "style-src 'self' 'unsafe-inline'; "  # CSS允许内联（Element Plus需要）
                    "img-src 'self' data: https:; "
                    "font-src 'self' data:; "
                    "connect-src 'self'; "
                    "frame-ancestors 'none'; "  # 禁止被iframe嵌入
                    "base-uri 'self'; "  # 限制base标签
                    "form-action 'self'; "  # 限制表单提交目标
                    "upgrade-insecure-requests;"  # 自动升级HTTP到HTTPS
                )
            else:
                # 开发环境：允许unsafe-inline和unsafe-eval（用于开发调试）
                csp = (
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                    "style-src 'self' 'unsafe-inline'; "
                    "img-src 'self' data: https:; "
                    "font-src 'self' data:; "
                    "connect-src 'self'; "
                    "frame-ancestors 'none';"
                )
            response.headers["Content-Security-Policy"] = csp

        # Strict-Transport-Security (HSTS): 强制HTTPS，防止中间人攻击
        # 生产环境启用，max-age=1年，包含子域名
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; "
                "includeSubDomains; "
                "preload"  # 允许浏览器预加载HSTS列表
            )

        # X-Download-Options: 防止IE浏览器自动打开下载文件
        response.headers["X-Download-Options"] = "noopen"

        # X-Permitted-Cross-Domain-Policies: 限制跨域策略文件
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    请求日志中间件
    记录所有API请求的详细信息，用于审计和调试
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.app = app

    async def dispatch(self, request: Request, call_next):
        # ====== 记录请求开始时间 ======
        start_time = time.time()

        # ====== 获取请求信息 ======
        try:
            from app.core.utils import get_client_ip
            client_ip = get_client_ip(request)
        except Exception as e:
            logger.warning(f"获取客户端IP失败: {e}，使用默认IP 'testclient'")
            client_ip = "testclient"

        method = request.method
        # URL 解码路径，使中文可读
        from urllib.parse import unquote
        path = unquote(request.url.path)
        # 生产环境不记录查询参数（可能包含敏感信息）
        query_params = str(request.query_params) if request.query_params and not settings.is_production else ""

        # ====== 记录请求日志（生产环境简化） ======
        if settings.is_production:
            # 生产环境：只记录关键信息，不记录敏感数据
            logger.info(
                f"请求开始: {method} {path} | IP: {client_ip}"
            )
        else:
            # 开发环境：记录详细信息
            logger.info(
                f"请求开始: {method} {path} | IP: {client_ip} | 查询参数: {query_params}"
            )

        # ====== 处理请求 ======
        try:
            response = await call_next(request)
            # ====== 计算处理时间 ======
            process_time = time.time() - start_time

            # ====== 记录响应日志 ======
            logger.info(
                f"请求完成: {method} {path} | "
                f"状态码: {response.status_code} | "
                f"处理时间: {process_time:.3f}秒 | "
                f"IP: {client_ip}"
            )

            # ====== 添加处理时间响应头 ======
            response.headers["X-Process-Time"] = f"{process_time:.3f}"

            return response
        except Exception as e:
            # ====== 记录异常 ======
            process_time = time.time() - start_time
            logger.error(
                f"请求异常: {method} {path} | "
                f"错误: {str(e)} | "
                f"处理时间: {process_time:.3f}秒 | "
                f"IP: {client_ip}",
                exc_info=True
            )
            raise


class CompressionMiddleware(BaseHTTPMiddleware):
    """
    响应压缩中间件
    对响应内容进行gzip压缩，减少网络传输量，特别适用于移动端
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.app = app
        # 最小压缩大小（小于此大小不压缩）
        self.min_compress_size = 500  # 500字节
        # 需要压缩的Content-Type
        self.compressible_types = {
            'application/json',
            'application/javascript',
            'text/css',
            'text/html',
            'text/plain',
            'text/xml',
            'application/xml',
        }

    def _should_compress(self, request: Request, response: Response) -> bool:
        """判断是否应该压缩响应"""
        # 检查Accept-Encoding头
        accept_encoding = request.headers.get("Accept-Encoding", "").lower()
        if "gzip" not in accept_encoding:
            return False

        # 检查Content-Type
        content_type = response.headers.get("Content-Type", "").lower()
        if not any(ct in content_type for ct in self.compressible_types):
            return False

        # 检查Content-Length（如果存在）
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) < self.min_compress_size:
            return False

        # 检查是否已经压缩
        if response.headers.get("Content-Encoding"):
            return False

        return True

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)

            # 判断是否需要压缩
            if not self._should_compress(request, response):
                return response

            # 读取响应体
            response_body = b""
            try:
                async for chunk in response.body_iterator:
                    response_body += chunk
            except Exception as e:
                logger.error(f"读取响应体时出错: {e}")
                # 如果读取失败，返回原始响应（可能已经被部分消费）
                return response

            # 如果响应体太小，不压缩
            if len(response_body) < self.min_compress_size:
                # 重新创建响应（因为body_iterator已被消费）
                return Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )

            # 压缩响应体
            try:
                compressed_body = gzip.compress(response_body, compresslevel=6)
            except Exception as e:
                logger.error(f"压缩响应体时出错: {e}")
                # 压缩失败，返回未压缩的响应
                return Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )

            # 更新响应头
            headers = dict(response.headers)
            headers["Content-Encoding"] = "gzip"
            headers["Content-Length"] = str(len(compressed_body))
            headers["Vary"] = "Accept-Encoding"

            # 返回压缩后的响应
            return Response(
                content=compressed_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type
            )
        except Exception as e:
            logger.error(f"压缩中间件处理请求时出错: {e}", exc_info=True)
            # 如果中间件出错，尝试继续处理（可能会失败，但至少不会导致服务崩溃）
            try:
                return await call_next(request)
            except:
                raise


def is_mobile_device(request: Request) -> bool:
    """
    检测是否为移动设备
    基于User-Agent判断
    """
    user_agent = request.headers.get("User-Agent", "").lower()
    mobile_keywords = [
        'mobile', 'android', 'iphone', 'ipad', 'ipod',
        'blackberry', 'windows phone', 'opera mini',
        'iemobile', 'palm', 'smartphone', 'tablet'
    ]
    return any(keyword in user_agent for keyword in mobile_keywords)


def get_device_type(request: Request) -> str:
    """
    获取设备类型
    返回: 'mobile', 'tablet', 'desktop'
    """
    user_agent = request.headers.get("User-Agent", "").lower()

    # 平板设备
    tablet_keywords = ['ipad', 'tablet', 'playbook', 'kindle']
    if any(keyword in user_agent for keyword in tablet_keywords):
        return 'tablet'

    # 移动设备
    mobile_keywords = [
        'mobile', 'android', 'iphone', 'ipod',
        'blackberry', 'windows phone', 'opera mini',
        'iemobile', 'palm', 'smartphone'
    ]
    if any(keyword in user_agent for keyword in mobile_keywords):
        return 'mobile'

    # 默认桌面设备
    return 'desktop'
