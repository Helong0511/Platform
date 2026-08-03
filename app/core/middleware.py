"""
安全中间件模块

功能说明：
提供FastAPI应用的安全中间件，包括：
- API限流：防止API滥用和暴力破解攻击
- 安全响应头：防止XSS、点击劫持等攻击
- 请求日志：记录所有API请求的详细信息
- 响应压缩：压缩响应内容，减少网络传输
- 性能监控：记录慢请求，优化性能

中间件执行顺序（从外到内）：
1. HTTPSRedirectMiddleware（生产环境强制HTTPS）
2. PerformanceMonitoringMiddleware（性能监控）
3. RequestLoggingMiddleware（请求日志）
4. CompressionMiddleware（响应压缩）
5. CSRFMiddleware（CSRF防护）
6. RateLimitMiddleware（API限流）
7. SecurityHeadersMiddleware（安全响应头）
8. CORSMiddleware（跨域处理）

API限流（RateLimitMiddleware）：
- 已登录用户（有效 access_token，含管理员与客户）：不限流
- 客户开放 API（/client_data、/client_products）：独立桶，默认 2000次/分钟
- 未登录其它接口：默认限流 100次/分钟（可配置）
- 登录接口（未带有效令牌）：5次/分钟（防止暴力破解）
- 短链接路由：不限流（支持高并发）
- 存储方式：优先使用Redis，降级到内存存储
- 限流标识：使用客户端IP地址

慢请求（PerformanceMonitoringMiddleware）：
- 2–3s：INFO；3–8s：WARNING；>8s：ERROR

安全响应头（SecurityHeadersMiddleware）：
- X-Content-Type-Options: nosniff（防止MIME类型嗅探）
- X-Frame-Options: DENY（防止点击劫持）
- X-XSS-Protection: 1; mode=block（启用XSS过滤器）
- Strict-Transport-Security: max-age=31536000（强制HTTPS）
- Content-Security-Policy: 限制资源加载来源

请求日志（RequestLoggingMiddleware）：
- 开发环境：记录请求开始/完成（含查询参数）
- 生产环境默认降噪：不记「请求开始」；仅记录 4xx/5xx、慢请求（LOG_ACCESS_SLOW_SECONDS）、异常
- /health 等探针成功请求可跳过；LOG_ACCESS_FULL_IN_PRODUCTION=true 可临时恢复全量
- 支持中文路径解码；生产不记录查询参数

响应压缩（CompressionMiddleware）：
- 使用gzip压缩响应内容
- 只压缩文本类型（JSON、HTML、CSS、JS等）
- 如果Nginx已配置压缩，可以禁用此中间件

性能监控（PerformanceMonitoringMiddleware）：
- 记录请求处理时间
- 慢请求警告（超过1秒）
- 在响应头中添加X-Process-Time

注意事项：
1. 中间件执行顺序很重要，后添加的中间件会先执行
2. 限流使用滑动窗口算法，支持多进程环境
3. 安全响应头在生产环境必须配置
4. 请求日志可能包含敏感信息，注意日志安全
5. 响应压缩会增加CPU开销，但减少网络传输
"""
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message
import time
import logging
import gzip
from io import BytesIO
import asyncio
# 类型注解已迁移到内置类型（Python 3.10+）
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional
from sqlalchemy import select
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.errors import ErrorCode, create_error_response
from app.core.redis_client import get_redis_client, reset_redis_client
from app.core.security import is_authenticated_request
from app.core.sensitive_path_guard import (
    HandleResult,
    handle_probe_hit,
    register_blocked_ip_cache_bust,
)
from app.core.sensitive_path_rules import level_label, match_sensitive_path
from app.core.utils import get_client_ip, get_device_type
from app.models.models import SensitivePathProbeLog, SensitiveBlockedIP
from urllib.parse import unquote

logger = logging.getLogger(__name__)

# ====== API限流存储 ======
# 内存降级：多进程不共享；生产应启用 Redis。此处限制 IP 条目数，防止探测撑爆内存。
_rate_limit_store: dict[str, dict[str, tuple[int, datetime]]] = defaultdict(dict)
_RATE_LIMIT_STORE_MAX_IPS = 10000
# Redis 限流异常日志限频（避免短时间刷屏）
_rate_limit_redis_error_log_window_seconds = 60
_rate_limit_redis_error_last_log_at: dict[str, float] = {}


def _evict_rate_limit_store_if_needed(now: datetime, window: int) -> None:
    """清理过期窗口；IP 数超上限时淘汰最久未活跃的条目。"""
    # 先清各 IP 下过期窗口，并删除空 IP
    empty_ips: list[str] = []
    for ip, windows in _rate_limit_store.items():
        expired = [
            key for key, (_count, ts) in windows.items()
            if (now - ts).total_seconds() > window
        ]
        for key in expired:
            del windows[key]
        if not windows:
            empty_ips.append(ip)
    for ip in empty_ips:
        _rate_limit_store.pop(ip, None)

    overflow = len(_rate_limit_store) - _RATE_LIMIT_STORE_MAX_IPS
    if overflow <= 0:
        return

    # 按该 IP 最近窗口时间排序，淘汰最旧的
    def _last_ts(ip: str) -> datetime:
        windows = _rate_limit_store.get(ip) or {}
        if not windows:
            return datetime.min.replace(tzinfo=timezone.utc)
        return max(ts for _c, ts in windows.values())

    stale_ips = sorted(_rate_limit_store.keys(), key=_last_ts)[:overflow]
    for ip in stale_ips:
        _rate_limit_store.pop(ip, None)


def _rate_limit_exceeded_response(*, limit: int, window: int) -> JSONResponse:
    """限流响应：与 API 标准错误体一致。"""
    body = create_error_response(
        ErrorCode.TOO_MANY_REQUESTS,
        message="请求过于频繁，请稍后再试",
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=body,
        headers={
            "Retry-After": str(window),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
        },
    )

# ====== 限流配置 ======
# 从配置中读取限流设置，提供默认值
DEFAULT_RATE_LIMIT = getattr(settings, 'API_RATE_LIMIT', 100)
DEFAULT_RATE_WINDOW = 60  # 秒

# 登录接口限流：从配置中读取，防止暴力破解
LOGIN_RATE_LIMIT = getattr(settings, 'LOGIN_RATE_LIMIT', 5)
LOGIN_RATE_WINDOW = 60

# 客户开放 API（签名鉴权）：独立桶 + 更高配额，避免翻页压测被普通 100/分钟限死
CLIENT_OPEN_API_RATE_LIMIT = getattr(settings, 'CLIENT_OPEN_API_RATE_LIMIT', 200)
# 已登录用户 API 配额（高于匿名，但仍有上限，防 Cookie 被盗滥用）
AUTHENTICATED_RATE_LIMIT = getattr(settings, 'AUTHENTICATED_RATE_LIMIT', 600)
_CLIENT_OPEN_API_PATHS = frozenset({
    "/api/v1/client_data",
    "/api/v1/client_products",
})


def _rate_limit_bucket(path: str, method: str) -> str:
    """按接口类别隔离限流计数，避免普通匿名请求耗尽登录配额。"""
    if path.endswith("/login") and method.upper() == "POST":
        return "login"
    if path == "/api/v1/audit-logs/client-error":
        return "client-error"
    if path in _CLIENT_OPEN_API_PATHS:
        return "client-open-api"
    return "api"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    API限流中间件
    防止API滥用和暴力破解攻击
    """

    def __init__(self, app: ASGIApp):
        """Args: app — 下游 ASGI 应用。"""
        super().__init__(app)
        self.app = app

    async def dispatch(self, request: Request, call_next):
        """
        对未登录请求按 IP 滑动窗口限流；已登录、短链与上报路由豁免。

        Returns:
            429 JSON 响应或下游处理器响应（附带 X-RateLimit-* 头）
        """
        # ====== 仅公开跳转/上报豁免限流；管理端短链 CRUD 仍受限流 ======
        # 已登录请求计入 auth-api 高配额桶（不再完全跳过）
        path = request.url.path
        is_public_tracking = (
            path.startswith("/s/")  # 公开短链重定向
            or path.startswith("/report")  # 点击上报
            or path.startswith("/change")  # 斗篷桥页切换
        )
        # 公开按 code 解析的只读接口（若存在）可豁免；管理列表/写操作不豁免
        if path.startswith("/api/v1/short-links/"):
            # /api/v1/short-links/{code} 形式的公开解析已迁到 /s/；此处一律按管理 API 限流
            is_public_tracking = False
        
        if is_public_tracking:
            response = await call_next(request)
            return response

        # 已登录：仍计入独立高配额桶，避免被盗用 Cookie 时无限打爆（不再完全跳过）
        authenticated = await is_authenticated_request(request)
        
        # ====== 获取客户端标识 ======
        # 使用IP地址作为限流标识（生产环境可结合用户ID）
        try:
            client_ip = get_client_ip(request)
        except Exception as e:
            logger.warning(f"获取客户端IP失败: {e}，使用默认IP 'testclient'")
            client_ip = "testclient"

        # ====== 按接口类别选择配额（运行时读 settings，便于本地压测提额） ======
        bucket = _rate_limit_bucket(path, request.method)
        if authenticated and bucket == "api":
            bucket = "auth-api"
            limit = int(getattr(settings, "AUTHENTICATED_RATE_LIMIT", AUTHENTICATED_RATE_LIMIT) or AUTHENTICATED_RATE_LIMIT)
            window = DEFAULT_RATE_WINDOW
        elif bucket == "login":
            limit = int(getattr(settings, "LOGIN_RATE_LIMIT", LOGIN_RATE_LIMIT) or LOGIN_RATE_LIMIT)
            window = LOGIN_RATE_WINDOW
        elif bucket == "client-open-api":
            limit = int(getattr(settings, "CLIENT_OPEN_API_RATE_LIMIT", CLIENT_OPEN_API_RATE_LIMIT) or CLIENT_OPEN_API_RATE_LIMIT)
            window = DEFAULT_RATE_WINDOW
        else:
            limit = int(getattr(settings, "API_RATE_LIMIT", DEFAULT_RATE_LIMIT) or DEFAULT_RATE_LIMIT)
            window = DEFAULT_RATE_WINDOW

        # ====== 生产环境：对敏感接口增加额外限流 ======
        if settings.is_production:
            sensitive_paths = ["/api/v1/auth/login", "/api/v1/users", "/api/v1/clients"]
            if any(path in request.url.path for path in sensitive_paths):
                # 敏感接口使用更严格的限流
                limit = min(limit, 30)  # 最多30次/分钟

        if path == "/api/v1/audit-logs/client-error":
            limit = min(limit, 10)

        # ====== 尝试使用Redis进行限流 ======
        redis_client = await get_redis_client()
        now = datetime.now(timezone.utc)
        current_window_key = f"{bucket}:{int(now.timestamp() / window)}"
        rate_limit_key = f"rate_limit:{bucket}:{client_ip}:{int(now.timestamp() / window)}"
        
        redis_counted = False
        updated_count = 0
        if redis_client:
            # Redis 计数与 call_next 分离，避免将 CSRF/业务 HTTPException 误判为 Redis 故障
            try:
                updated_count = int(await redis_client.incr(rate_limit_key))
                if updated_count == 1:
                    await redis_client.expire(rate_limit_key, window)
                redis_counted = True
            except Exception as e:
                error_msg = str(e) or repr(e) or "未知错误"
                error_type = type(e).__name__
                now_ts = time.time()
                error_key = f"{error_type}:{error_msg[:120]}"
                last_log_at = _rate_limit_redis_error_last_log_at.get(error_key, 0.0)
                should_log = (now_ts - last_log_at) >= _rate_limit_redis_error_log_window_seconds
                if should_log:
                    logger.warning(f"Redis限流操作失败: {error_type} - {error_msg}，回退到内存存储")
                    _rate_limit_redis_error_last_log_at[error_key] = now_ts
                else:
                    logger.debug(f"Redis限流异常抑制日志: {error_type} - {error_msg}")
                await reset_redis_client(f"RateLimitMiddleware: {error_type}")

        if redis_counted:
            if updated_count > limit:
                logger.warning(f"API限流触发（Redis）: IP={client_ip}, 路径={request.url.path}, 限制={limit}/{window}秒")
                return _rate_limit_exceeded_response(limit=limit, window=window)

            response = await call_next(request)
            remaining = max(0, limit - updated_count)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(int((now + timedelta(seconds=window)).timestamp()))
            return response
        
        # ====== 使用内存存储进行限流（Redis不可用时；多进程不共享） ======
        _evict_rate_limit_store_if_needed(now, window)
        client_requests = _rate_limit_store[client_ip]

        # 统计当前窗口的请求数
        current_count, _ = client_requests.get(current_window_key, (0, now))

        # ====== 检查是否超过限制 ======
        if current_count >= limit:
            logger.warning(f"API限流触发（内存）: IP={client_ip}, 路径={request.url.path}, 限制={limit}/{window}秒")
            return _rate_limit_exceeded_response(limit=limit, window=window)

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
    记录慢请求和查询性能，提供详细的性能指标
    """
    
    def __init__(self, app: ASGIApp):
        """初始化慢请求阈值与进程内累计统计计数器。"""
        super().__init__(app)
        self.app = app
        self.slow_request_threshold = 3.0  # 慢请求 WARNING 阈值（秒）
        self.very_slow_request_threshold = 8.0  # 非常慢请求 ERROR 阈值（秒）
        # 导出类接口允许更长耗时，超过极慢阈值只记 WARNING，避免刷 ERROR
        self.heavy_path_prefixes = (
            "/api/v1/excel/export",
        )

        # 本进程兜底计数（重启丢失；跨 Worker 聚合见 monitoring_redis / SystemMonitor）
        self.request_count = 0
        self.total_process_time = 0.0
        self.slow_request_count = 0
        self.very_slow_request_count = 0

    async def dispatch(self, request: Request, call_next):
        """记录请求耗时，慢请求分级写日志，响应头附加 X-Process-Time。"""
        start_time = time.time()
        
        # 处理请求
        try:
            response = await call_next(request)
        except Exception as e:
            # 即使请求失败，也记录处理时间
            process_time = time.time() - start_time
            self._log_performance(request, process_time, failed=True, error=str(e))
            raise
        
        # 计算处理时间
        process_time = time.time() - start_time
        
        # 更新本进程统计（仅作 Redis 不可用时的响应头兜底）
        self.request_count += 1
        self.total_process_time += process_time
        
        # 记录慢请求
        path = request.url.path or ""
        is_heavy = any(path.startswith(p) for p in self.heavy_path_prefixes)
        if process_time > self.very_slow_request_threshold:
            self.very_slow_request_count += 1
            # 导出等已知重接口不以 ERROR 刷屏
            level = "warning" if is_heavy else "error"
            self._log_performance(request, process_time, level=level)
        elif process_time > self.slow_request_threshold:
            self.slow_request_count += 1
            self._log_performance(request, process_time, level="warning")
        elif process_time > 2.0:
            self._log_performance(request, process_time, level="info")
        
        # 添加性能响应头
        response.headers["X-Process-Time"] = f"{process_time:.4f}"
        
        # 每 100 次附带聚合头：优先 Redis 跨 Worker 汇总，避免仅看本进程且重启归零
        if self.request_count % 100 == 0:
            avg_time = 0.0
            slow_count = self.slow_request_count
            try:
                from app.core.monitoring_redis import get_cached_redis_api_totals

                redis_totals = get_cached_redis_api_totals()
                req = int(redis_totals.get("request_count") or 0)
                if req > 0:
                    avg_time = float(redis_totals.get("total_duration") or 0) / req
                    slow_count = int(redis_totals.get("slow_request_count") or 0)
                elif self.request_count > 0:
                    avg_time = self.total_process_time / self.request_count
            except Exception:
                if self.request_count > 0:
                    avg_time = self.total_process_time / self.request_count
            response.headers["X-Avg-Process-Time"] = f"{avg_time:.4f}"
            response.headers["X-Slow-Request-Count"] = str(slow_count)
        
        return response
    
    def _log_performance(self, request: Request, process_time: float, level: str = "warning", failed: bool = False, error: str = None):
        """记录性能信息"""
        try:
            client_ip = get_client_ip(request)
        except Exception:
            client_ip = "unknown"
        
        try:
            device_type = get_device_type(request)
        except Exception:
            device_type = "unknown"
        
        user_agent = request.headers.get("User-Agent", "未知")
        path = unquote(request.url.path)
        
        log_message = (
            f"{'失败请求' if failed else '慢请求'}: {request.method} {path} "
            f"耗时 {process_time:.3f}s, IP: {client_ip}, 设备: {device_type}, UA: {user_agent}"
        )
        
        if error:
            log_message += f", 错误: {error}"
        
        # 添加查询参数信息（如果有）
        if request.query_params and not settings.is_production:
            log_message += f", 参数: {dict(request.query_params)}"
        
        if level == "error":
            logger.error(log_message)
        elif level == "info":
            logger.info(log_message)
        else:
            logger.warning(log_message)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    安全响应头中间件
    添加安全相关的HTTP响应头，防止XSS、点击劫持等攻击
    """

    def __init__(self, app: ASGIApp):
        """Args: app — 下游 ASGI 应用。"""
        super().__init__(app)
        self.app = app

    async def dispatch(self, request: Request, call_next):
        """为所有响应附加 CSP、HSTS、Referrer-Policy 等安全头。"""
        response = await call_next(request)

        # ====== 安全响应头（防止网络劫持和XSS攻击） ======
        # X-Content-Type-Options: 防止MIME类型嗅探
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options: 防点击劫持（与 CSP frame-ancestors 双轨；扫描器/旧浏览器仍依赖此头）
        if not response.headers.get("X-Frame-Options"):
            response.headers["X-Frame-Options"] = "DENY"

        # 现代浏览器优先遵循 Content-Security-Policy 的 frame-ancestors
        # X-XSS-Protection 已过时，不再设置

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
                path = request.url.path or ""
                # 桥页/静态桥资源依赖内联脚本；其它 HTML 生产环境禁用 unsafe-inline
                needs_inline_script = (
                    path.startswith("/change")
                    or path.startswith("/bridge")
                    or "/change/" in path
                )
                if settings.is_production:
                    script_src = (
                        "script-src 'self' 'unsafe-inline'; "
                        if needs_inline_script
                        else "script-src 'self'; "
                    )
                    csp = (
                        "default-src 'self'; "
                        f"{script_src}"
                        "script-src-attr 'none'; "
                        "object-src 'none'; "
                        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
                        "img-src 'self' data: https:; "
                        "font-src 'self' data: https://cdnjs.cloudflare.com; "
                        "connect-src 'self'; "
                        "frame-ancestors 'none'; "
                        "base-uri 'self'; "
                        "form-action 'self'; "
                        "upgrade-insecure-requests;"
                    )
                else:
                    # 开发环境：允许unsafe-inline和unsafe-eval（用于开发调试）
                    csp = (
                        "default-src 'self'; "
                        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                        "script-src-attr 'none'; "
                        "object-src 'none'; "
                        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
                        "img-src 'self' data: https:; "
                        "font-src 'self' data: https://cdnjs.cloudflare.com; "
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
    请求访问日志中间件。

    开发环境：记录请求开始/完成（含查询参数）。
    生产环境默认降噪：不记「请求开始」；仅记录异常、4xx/5xx、或超过慢请求阈值的完成日志。
    健康检查等探针路径可跳过。可通过 LOG_ACCESS_FULL_IN_PRODUCTION=true 恢复全量。
    """

    # 生产环境默认可跳过的低价值路径（精确或前缀）
    _SKIP_PATH_SUFFIXES = (
        "/health",
        "/favicon.ico",
    )

    def __init__(self, app: ASGIApp):
        """绑定 access 专用 logger，与业务 logger 分离。"""
        super().__init__(app)
        self.app = app
        self.access_logger = logging.getLogger("access")

    def _should_skip_path(self, path: str) -> bool:
        path_l = (path or "").lower()
        return any(path_l.endswith(suffix) for suffix in self._SKIP_PATH_SUFFIXES)

    def _slow_threshold_seconds(self) -> float:
        try:
            return float(getattr(settings, "LOG_ACCESS_SLOW_SECONDS", 3.0) or 3.0)
        except (TypeError, ValueError):
            return 3.0

    def _full_access_logging(self) -> bool:
        """是否全量记录 access（开发默认全量；生产需显式打开）。"""
        if not settings.is_production:
            return True
        return bool(getattr(settings, "LOG_ACCESS_FULL_IN_PRODUCTION", False))

    async def dispatch(self, request: Request, call_next):
        """记录请求方法、路径、状态码与耗时；生产默认仅记录异常/错误/慢请求。"""
        start_time = time.time()

        try:
            client_ip = get_client_ip(request)
        except Exception as e:
            logger.warning(f"获取客户端IP失败: {e}，使用默认IP 'testclient'")
            client_ip = "testclient"

        method = request.method
        path = unquote(request.url.path)
        query_params = str(request.query_params) if request.query_params and not settings.is_production else ""
        user_agent = request.headers.get("User-Agent", "未知")
        try:
            device_type = get_device_type(request)
        except Exception:
            device_type = "未知"

        skip_path = self._should_skip_path(path)
        full_logging = self._full_access_logging()

        if full_logging and not skip_path:
            if settings.is_production:
                self.access_logger.info(
                    f"请求开始: {method} {path} | IP: {client_ip} | 设备: {device_type} | UA: {user_agent}"
                )
            else:
                self.access_logger.info(
                    f"请求开始: {method} {path} | IP: {client_ip} | 设备: {device_type} | "
                    f"UA: {user_agent} | 查询参数: {query_params}"
                )

        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            status_code = int(getattr(response, "status_code", 0) or 0)
            slow = process_time >= self._slow_threshold_seconds()
            is_error_status = status_code >= 400

            should_log_complete = False
            if skip_path:
                should_log_complete = is_error_status
            elif full_logging:
                should_log_complete = True
            else:
                # 生产降噪：仅错误状态或慢请求
                should_log_complete = is_error_status or slow

            if should_log_complete:
                msg = (
                    f"请求完成: {method} {path} | "
                    f"状态码: {status_code} | "
                    f"处理时间: {process_time:.3f}秒 | "
                    f"IP: {client_ip} | 设备: {device_type}"
                )
                if is_error_status:
                    self.access_logger.warning(msg)
                elif slow:
                    self.access_logger.warning(msg)
                else:
                    self.access_logger.info(msg)

            response.headers["X-Process-Time"] = f"{process_time:.3f}"
            return response
        except Exception as e:
            process_time = time.time() - start_time
            self.access_logger.warning(
                f"请求异常: {method} {path} | "
                f"错误类型: {type(e).__name__} | "
                f"处理时间: {process_time:.3f}秒 | "
                f"IP: {client_ip} | 设备: {device_type}"
            )
            raise


class CompressionMiddleware(BaseHTTPMiddleware):
    """
    响应压缩中间件
    对响应内容进行gzip压缩，减少网络传输量，特别适用于移动端
    """

    def __init__(self, app: ASGIApp):
        """配置最小压缩体积与可压缩的 Content-Type 白名单。"""
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
        """对 JSON/HTML 等文本响应做 gzip 压缩（客户端须支持 Accept-Encoding: gzip）。"""
        try:
            response = await call_next(request)

            # ---------- 判断是否需要压缩 ----------
            if not self._should_compress(request, response):
                return response

            # 读取响应体
            response_body = b""
            try:
                async for chunk in response.body_iterator:
                    response_body += chunk
            except Exception as e:
                logger.error(f"读取响应体时出错: {e}")
                return Response(
                    content=b"",
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

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
        except StarletteHTTPException:
            raise
        except Exception as e:
            logger.error(f"压缩中间件处理请求时出错: {e}", exc_info=True)
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


class StreamErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    流异常处理中间件
    在 Starlette 的异常处理中间件之前捕获并静默处理流关闭异常（EndOfStream）
    这些异常通常表示客户端提前关闭了连接，是正常情况，不应该记录为错误
    """
    
    def __init__(self, app: ASGIApp):
        """Args: app — 下游 ASGI 应用。"""
        super().__init__(app)
        self.app = app

    def _is_stream_error(self, exc: Exception) -> bool:
        """
        检查异常是否是流关闭相关的异常（客户端提前关闭连接）
        
        Args:
            exc: 异常对象
        
        Returns:
            如果是流异常返回True，否则返回False
        """
        error_type = type(exc).__name__
        error_module = type(exc).__module__
        return ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                "anyio" in error_module)
    
    async def dispatch(self, request: Request, call_next):
        """
        处理请求，捕获流关闭异常并静默处理
        """
        try:
            return await call_next(request)
        except Exception as exc:
            # 检查是否是流关闭异常
            if self._is_stream_error(exc):
                # 流关闭异常是正常的（客户端提前关闭连接），不需要记录错误
                # 直接重新抛出，让 ASGI 服务器处理，但不记录为错误
                logger.debug(f"客户端提前关闭连接: {request.method} {request.url.path}")
                raise exc
            
            # 检查异常链中是否有流异常
            context_exc = None
            if hasattr(exc, '__context__') and exc.__context__:
                if self._is_stream_error(exc.__context__):
                    context_exc = exc.__context__
            if not context_exc and hasattr(exc, '__cause__') and exc.__cause__:
                if self._is_stream_error(exc.__cause__):
                    context_exc = exc.__cause__
            
            if context_exc:
                # 如果异常链中有流异常，说明连接已断开
                logger.debug(f"检测到连接断开上下文: {request.method} {request.url.path}")
                # 直接重新抛出流异常，让 ASGI 服务器处理
                raise context_exc from None
            
            # 其他异常，继续传播
            raise exc


# ====== 敏感路径防护（分级规则见 app.core.sensitive_path_rules） ======


class SensitivePathGuardMiddleware(BaseHTTPMiddleware):
    """
    分级拦截敏感路径探测：低危仅记录，中高危累计自动封禁，危急触发 Telegram 预警。
    规则与等级定义见 sensitive_path_rules.py。
    """

    def __init__(self, app: ASGIApp):
        """初始化 IP 黑名单短 TTL 缓存，并注册封禁后的缓存失效回调。"""
        super().__init__(app)
        self._blocked_ip_cache: set[str] = set()
        self._blocked_ip_cache_expires_at: float = 0.0
        self._blocked_ip_cache_ttl_seconds: float = 30.0
        self._blocked_ip_lock = asyncio.Lock()
        register_blocked_ip_cache_bust(self._invalidate_blocked_ip_cache)

    def _invalidate_blocked_ip_cache(self) -> None:
        """封禁 IP 变更时使本地缓存立即过期，下次请求重新拉 Redis。"""
        self._blocked_ip_cache_expires_at = 0.0

    async def _persist_probe_log(
        self,
        *,
        request: Request,
        client_ip: str,
        matched_rule: str,
        severity_level: int,
        action_taken: str,
    ) -> None:
        """持久化敏感路径拦截日志（失败不影响主流程）。"""
        try:
            async with AsyncSessionLocal() as db:
                db.add(
                    SensitivePathProbeLog(
                        request_path=(request.url.path or "")[:1024],
                        method=(request.method or "")[:16],
                        client_ip=(client_ip or "unknown")[:64],
                        user_agent=(request.headers.get("user-agent") or "")[:512],
                        query_string=(request.url.query or "")[:2048],
                        matched_rule=matched_rule[:255],
                        severity_level=int(severity_level),
                        action_taken=(action_taken or "")[:64],
                    )
                )
                await db.commit()
        except Exception as exc:
            logger.warning("敏感路径拦截日志入库失败: %s", exc)

    async def _is_blocked_ip(self, client_ip: str) -> bool:
        """检查是否命中IP黑名单（带短TTL缓存）。"""
        if not client_ip:
            return False
        now_ts = time.time()
        if now_ts > self._blocked_ip_cache_expires_at:
            async with self._blocked_ip_lock:
                if now_ts > self._blocked_ip_cache_expires_at:
                    try:
                        async with AsyncSessionLocal() as db:
                            result = await db.execute(
                                select(SensitiveBlockedIP.blocked_ip).where(
                                    SensitiveBlockedIP.is_active == True
                                )
                            )
                            self._blocked_ip_cache = {
                                (row[0] or "").strip()
                                for row in result.all()
                                if (row[0] or "").strip()
                            }
                    except Exception as exc:
                        logger.warning("加载敏感路径IP黑名单失败: %s", exc)
                        self._blocked_ip_cache = set()
                    finally:
                        self._blocked_ip_cache_expires_at = now_ts + self._blocked_ip_cache_ttl_seconds
        return client_ip in self._blocked_ip_cache

    async def dispatch(self, request: Request, call_next):
        """
        匹配敏感路径规则：黑名单 IP 返回 403，命中规则返回 404 并累计计数/自动封禁。

        Returns:
            JSONResponse（拦截）或下游正常响应
        """
        if not getattr(settings, "ENABLE_SENSITIVE_PATH_GUARD", True):
            return await call_next(request)

        # ---------- 解析客户端 IP ----------
        try:
            client_ip = get_client_ip(request)
        except Exception:
            client_ip = "unknown"

        # 本机回环永不按黑名单拒绝，避免本地联调/安全回归被锁死
        from app.core.sensitive_path_guard import _is_loopback_ip

        if (not _is_loopback_ip(client_ip)) and await self._is_blocked_ip(client_ip):
            logger.warning("黑名单IP请求已拦截: path=%s ip=%s", request.url.path, client_ip)
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Forbidden"},
            )

        path_raw = request.url.path or ""
        path_l = path_raw.lower()
        # GAM 定时任务管理端接口（含密钥上传），勿按敏感路径子串误拦
        if "/api/v1/scheduled-tasks/" in path_l and (
            "/gam-config" in path_l
            or "/gam-secrets/" in path_l
            or "/gam-report-types/" in path_l
        ):
            return await call_next(request)

        match = match_sensitive_path(path_raw)

        if match:
            handle_result: HandleResult = await handle_probe_hit(
                client_ip=client_ip,
                path=path_raw,
                match=match,
            )
            log_msg = (
                "敏感路径探测已拦截 [%s]: path=%s ip=%s rule=%s action=%s hits=%s ua=%s"
            )
            log_args = (
                level_label(int(match.level)),
                path_raw,
                client_ip,
                match.matched_rule,
                handle_result.action_taken,
                handle_result.hit_count,
                (request.headers.get("user-agent") or "")[:120],
            )
            logger.log(match.policy.log_level, log_msg, *log_args)

            await self._persist_probe_log(
                request=request,
                client_ip=client_ip,
                matched_rule=match.matched_rule,
                severity_level=int(match.level),
                action_taken=handle_result.action_taken,
            )
            return JSONResponse(
                status_code=match.policy.http_status,
                content={"detail": "Not Found"},
            )

        return await call_next(request)