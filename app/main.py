"""
FastAPI 应用主入口模块。

功能说明：
- 创建 FastAPI 应用实例，配置 lifespan（数据库、Redis、调度器、Telegram Bot）
- 注册中间件链：HTTPS、性能监控、日志、CSRF、限流、安全头、敏感路径防护
- 挂载 ``api_v1`` 路由、短链接公开路由、静态资源与全局异常处理器

在系统中的位置：
- 由 uvicorn/gunicorn 以 ``app.main:app`` 启动；是整个后端进程的组装根
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from app.api_v1 import api_router
from app.bootstrap.exception_handlers import register_exception_handlers
from app.bootstrap.lifespan import lifespan
from app.bootstrap.logging_setup import configure_logging
from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.core.https_middleware import HTTPSRedirectMiddleware
from app.core.middleware import (
    PerformanceMonitoringMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    SensitivePathGuardMiddleware,
    StreamErrorHandlingMiddleware,
)
from app.core.monitoring import SystemMonitoringMiddleware

logger = configure_logging()

# ====== 初始化FastAPI应用 ======
# 生产环境禁用API文档
app = FastAPI(
    title=settings.SERVER_NAME,
    description=settings.SERVER_DESCRIPTION,
    version="1.0.0",
    docs_url=None if settings.is_production else f"{settings.API_V1_STR}/docs",
    redoc_url=None if settings.is_production else f"{settings.API_V1_STR}/redoc",
    openapi_url=None if settings.is_production else f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,  # 使用 lifespan 替代已弃用的 @app.on_event()
)

# ====== 添加安全中间件 ======
# 注意：中间件的添加顺序很重要，后添加的中间件会先执行

# 0. 流异常处理中间件（最外层，静默处理客户端提前关闭连接的异常）
app.add_middleware(StreamErrorHandlingMiddleware)

# 0.5 敏感路径防护（防 .env / wp-admin 等扫描；生产环境屏蔽文档路径探测）
if settings.ENABLE_SENSITIVE_PATH_GUARD:
    app.add_middleware(SensitivePathGuardMiddleware)

# 1. HTTPS强制重定向中间件（生产环境强制HTTPS）
if settings.is_production:
    app.add_middleware(HTTPSRedirectMiddleware)

# 2. 性能监控中间件（记录慢请求）
app.add_middleware(PerformanceMonitoringMiddleware)

# 2.5 系统监控数据采集（供 /api/v1/monitoring 仪表盘使用）
app.add_middleware(SystemMonitoringMiddleware)

# 3. 请求日志中间件（记录所有请求）
app.add_middleware(RequestLoggingMiddleware)

# 4. 响应压缩中间件（减少网络传输量，特别适用于移动端）
# 注意：如果 Nginx 已配置 gzip 压缩，可以禁用此中间件以提高性能
# 暂时禁用，由 Nginx 处理压缩（更高效）
# app.add_middleware(CompressionMiddleware)

# 5. CSRF防护中间件（防止CSRF攻击）
# 生产环境强制启用，忽略 ENABLE_CSRF=false（防止误关）
_csrf_enabled = settings.ENABLE_CSRF or settings.is_production
if settings.is_production and not settings.ENABLE_CSRF:
    logger.warning("生产环境检测到 ENABLE_CSRF=false，已强制启用 CSRF 防护")
if _csrf_enabled:
    app.add_middleware(CSRFMiddleware)
    logger.info("CSRF防护已启用")
else:
    logger.warning("CSRF防护已关闭（仅非生产环境允许）")

# 6. API限流中间件（防止API滥用）
app.add_middleware(RateLimitMiddleware)

# 7. 安全响应头中间件（防止XSS、点击劫持等）
app.add_middleware(SecurityHeadersMiddleware)

# 7. CORS中间件（处理跨域请求，生产环境严格配置）
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,  # 允许携带凭证（cookies）
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],  # 限制HTTP方法
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "Accept",
            "Origin",
            "X-CSRF-Token"  # CSRF令牌（如果使用）
        ],  # 限制请求头
        expose_headers=[
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-Process-Time",
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-CSRF-Token"  # 暴露CSRF令牌响应头
        ],  # 暴露的响应头
        max_age=3600,  # 预检请求缓存时间（1小时）
    )



# ====== 全局异常处理 ======
register_exception_handlers(app)

# 根路由健康检查
@app.get("/")
async def root():
    """根路径健康检查，供负载均衡或运维探测服务存活。"""
    return {
        "status": "success",
        "message": f"{settings.SERVER_NAME} is running",
        "version": "1.0.0"
    }


@app.get(f"{settings.API_V1_STR}/health", tags=["系统"])
async def api_health_check():
    """API 存活探测（不访问数据库），供本地开发确认后端已启动。"""
    return {"status": "ok"}

# 处理 favicon.ico 请求
@app.get("/favicon.ico")
async def favicon():
    """返回站点 favicon；生产用 /data/Platform/scripts，开发环境回退到项目 scripts 目录。"""
    # 优先使用服务器路径，本地开发时会自动回退到本地路径
    favicon_path = "/data/Platform/scripts/favicon.ico"
    
    # 如果服务器路径不存在，尝试本地路径（用于开发环境）
    if not os.path.exists(favicon_path):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        favicon_path = os.path.join(current_dir, "..", "scripts", "favicon.ico")
    
    if os.path.exists(favicon_path):
        return FileResponse(
            favicon_path,
            media_type="image/x-icon",
            headers={
                "Cache-Control": "public, max-age=31536000, immutable"
            }
        )
    else:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})


# ====== 注册路由 ======
# 包含API路由
app.include_router(api_router, prefix=settings.API_V1_STR)

# 短链接重定向路由（公开访问，无需认证）
from app.routes.short_link import router as short_link_redirect_router

logger.info("使用模块化短链接路由（app/routes/short_link/）")
app.include_router(short_link_redirect_router)

if __name__ == "__main__":
    import uvicorn

    # 直接 python -m / 本文件启动仅供本机开发；生产必须走 Gunicorn+Nginx
    _dev_host = "127.0.0.1" if settings.is_production else os.getenv("DEV_BIND_HOST", "127.0.0.1")
    if settings.is_production:
        logger.error("生产环境禁止以 __main__ + reload 方式启动，请使用 Gunicorn")
        raise SystemExit(1)
    uvicorn.run(
        "app.main:app",
        host=_dev_host,
        port=8960,
        reload=True,
        reload_dirs=["app"],
        log_level="info",
        access_log=False,  # 禁用 uvicorn 的默认访问日志，使用我们的 RequestLoggingMiddleware（支持中文路径解码）
        proxy_headers=False,
    )