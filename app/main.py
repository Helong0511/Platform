"""
FastAPI应用主入口
配置应用、中间件、路由、异常处理等
"""
import warnings
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.config import settings
from app.core.errors import ErrorCode, create_error_response
from app.core.middleware import RateLimitMiddleware, SecurityHeadersMiddleware, RequestLoggingMiddleware, \
    CompressionMiddleware, PerformanceMonitoringMiddleware
from app.core.https_middleware import HTTPSRedirectMiddleware
from app.core.timezone_utils import log_timezone_info, check_and_validate_timezone
from app.api.api_v1 import api_router
import logging
from logging.handlers import RotatingFileHandler
import os
import asyncio
import base64
# 抑制 APScheduler 的 pkg_resources 弃用警告
# 这是 APScheduler 库内部使用已弃用的 pkg_resources 导致的警告
# 不影响功能，等待库更新修复
warnings.filterwarnings('ignore', message='.*pkg_resources is deprecated.*', category=UserWarning)

# 确保日志目录存在
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(log_dir, exist_ok=True)

# ====== 配置根日志记录器 ======
# 这样所有子模块的日志都会被记录
root_logger = logging.getLogger()
# 生产环境使用WARNING级别，开发环境使用INFO级别
# 但允许通过环境变量 LOG_LEVEL 覆盖
log_level = settings.LOG_LEVEL if hasattr(settings, 'LOG_LEVEL') else ("WARNING" if settings.is_production else "INFO")
root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

# 创建轮转文件处理器
file_handler = RotatingFileHandler(
    os.path.join(log_dir, 'app.log'),
    maxBytes=1024 * 1024 * 5,  # 5MB
    backupCount=5,
    encoding='utf-8'
)
# 多进程环境优化：在日志中包含进程ID，便于区分不同 worker
formatter = logging.Formatter(
    '%(asctime)s - [PID:%(process)d] - %(name)s - %(levelname)s - %(message)s'
)
file_handler.setFormatter(formatter)
file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

# 添加到根日志记录器（这样所有子模块的日志都会被记录）
root_logger.addHandler(file_handler)


# 重定向 stdout 和 stderr 到日志文件（捕获 print() 输出）
# 这样任务函数中的 print() 也会写入日志文件
class LoggingStream:
    """将 stdout/stderr 重定向到日志文件"""

    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level

    def write(self, message):
        if message and message.strip():  # 忽略空行
            # 移除换行符，logger 会自动添加
            message = message.rstrip('\n\r')
            if message:
                self.logger.log(self.log_level, f"[STDOUT] {message}")

    def flush(self):
        pass


# 创建专门的 logger 用于捕获 stdout/stderr
stdout_logger = logging.getLogger('stdout')
stdout_logger.setLevel(logging.INFO)
stdout_logger.addHandler(file_handler)
stdout_logger.propagate = False  # 防止重复输出

stderr_logger = logging.getLogger('stderr')
stderr_logger.setLevel(logging.WARNING)
stderr_logger.addHandler(file_handler)
stderr_logger.propagate = False  # 防止重复输出

# 重定向 stdout 和 stderr（生产环境也重定向，确保 print() 输出被记录）
import sys

sys.stdout = LoggingStream(stdout_logger, logging.INFO)
sys.stderr = LoggingStream(stderr_logger, logging.WARNING)

# 防止日志重复输出（如果已经有handler，不添加console handler）
if not root_logger.handlers or not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
    # 开发环境也输出到控制台
    if not settings.is_production:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)

# 获取当前模块的日志记录器（用于向后兼容）
logger = logging.getLogger(__name__)


# ====== 应用生命周期管理 ======
# 使用 lifespan 上下文管理器替代已弃用的 @app.on_event()
# 这是 FastAPI 0.95.0+ 推荐的方式，提供更好的资源管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    启动时初始化数据库，关闭时清理资源
    """
    # ====== 启动时执行 ======
    import os
    worker_pid = os.getpid()
    logger.info(f"[Worker PID:{worker_pid}] 应用启动中...")
    
    # 检查并验证时区配置（启动时首先检查）
    try:
        timezone_consistent = check_and_validate_timezone()
        if not timezone_consistent:
            logger.warning(
                f"[Worker PID:{worker_pid}] 系统时区与配置时区不一致，"
                "应用将使用配置的时区处理所有时间操作"
            )
        # 记录详细的时区信息
        log_timezone_info()
    except Exception as e:
        logger.warning(f"时区检查时出错: {e}，继续启动...")

    # 确保数据库存在并创建表（多进程环境：每个 worker 都会执行，但数据库操作是安全的）
    try:
        from app.db.database import create_database
        from app.models.models import Base
        from app.core.database import engine

        # 创建数据库（如果不存在）
        await create_database()

        # 创建所有表（如果不存在，使用 IF NOT EXISTS 语义）
        # 导入所有模型以确保SQLAlchemy能够发现所有表
        from app.models import (
            User, Client, Product, AdData, ProductAssignment, 
            ScheduledTask, UserAuditLog, UserSession, TokenBlacklist
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info(f"[Worker PID:{worker_pid}] 数据库表创建完成")
    except Exception as e:
        logger.error(f"[Worker PID:{worker_pid}] 数据库表创建失败: {e}", exc_info=True)
        # 不抛出异常，允许应用继续启动（可能是表已存在或其他 worker 已创建）
        logger.warning(f"[Worker PID:{worker_pid}] 继续启动应用...")
    
    # 初始化数据库，创建默认管理员账户
    try:
        from app.core.database import init_db
        await init_db()
        logger.info(f"[Worker PID:{worker_pid}] 数据库初始化完成（包括默认管理员账户）")
    except Exception as e:
        logger.error(f"[Worker PID:{worker_pid}] 数据库初始化失败: {e}", exc_info=True)
        # 不抛出异常，允许应用继续启动

    # 初始化Redis连接（如果配置了）
    try:
        from app.core.redis_client import get_redis_client
        redis_client = await get_redis_client()
        if redis_client:
            logger.info(f"[Worker PID:{worker_pid}] Redis连接已初始化")
        else:
            logger.info(f"[Worker PID:{worker_pid}] Redis未配置，使用内存存储")
    except Exception as e:
        logger.warning(f"[Worker PID:{worker_pid}] Redis初始化失败: {e}，将使用内存存储")

    # 初始化定时任务（多进程环境：每个 worker 独立初始化调度器）
    try:
        from app.scheduler_module import init_scheduled_tasks, start_scheduler
        from app.scheduler_module.task_init import init_scheduled_tasks_in_db
        import os
        worker_pid = os.getpid()
        logger.info(f"[Worker PID:{worker_pid}] 开始初始化定时任务...")
        
        # 首先检查并添加任务到数据库（确保所有配置的任务都在数据库中有记录）
        try:
            await init_scheduled_tasks_in_db()
        except Exception as db_init_error:
            logger.warning(f"[Worker PID:{worker_pid}] 初始化任务到数据库失败: {db_init_error}，继续启动...")
        
        # 然后初始化调度器
        await init_scheduled_tasks()
        logger.info(f"[Worker PID:{worker_pid}] 定时任务初始化完成，正在启动调度器...")
        await start_scheduler()
        logger.info(f"[Worker PID:{worker_pid}] 定时任务调度器已启动")
    except Exception as e:
        import os
        worker_pid = os.getpid()
        logger.error(f"[Worker PID:{worker_pid}] 定时任务初始化失败: {e}", exc_info=True)
        logger.warning(f"[Worker PID:{worker_pid}] 应用将继续启动，但定时任务功能可能不可用")

    # 初始化Telegram Bot（使用文件锁确保只有一个进程启动）
    try:
        # 检查是否启用 Telegram
        telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
        if not telegram_enabled:
            logger.info(f"[Worker PID:{os.getpid()}] Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false），跳过启动")
        else:
            from app.core.auto_bot import start_bot, send_telegram_message, bot_initialized
            import os
            worker_pid = os.getpid()
            
            if bot_initialized:
                logger.info(f"[Worker PID:{worker_pid}] 尝试启动 Telegram 机器人线程...")
                start_success = start_bot()
                if start_success:
                    # 延迟发送启动消息，确保 Bot 已完全启动
                    await asyncio.sleep(2)  # 等待2秒确保 Bot 连接建立
                    # send_telegram_message 内部已有完整的容错处理
                    await send_telegram_message("✅ Telegram 机器人已启动")
                else:
                    logger.info(f"[Worker PID:{worker_pid}] Telegram 机器人未启动（其他进程可能已启动或未获取到锁）")
            else:
                logger.info(f"[Worker PID:{worker_pid}] Telegram Bot 未配置（TELEGRAM_TOKEN 未设置），跳过启动")
    except Exception as e:
        import os
        worker_pid = os.getpid()
        logger.error(f"[Worker PID:{worker_pid}] 启动 Telegram 机器人初始化失败: {e}", exc_info=True)
        logger.warning(f"[Worker PID:{worker_pid}] 应用将继续启动，但Telegram 机器人可能不可用")

    logger.info("应用启动完成")

    # ====== 应用运行期间 ======
    yield

    # ====== 关闭时执行 ======
    logger.info("应用关闭中...")
    try:
        # 关闭定时任务调度器
        from app.scheduler_module import shutdown_scheduler
        await shutdown_scheduler()
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("定时任务调度器关闭时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭定时任务调度器时出现错误: {e}")

    try:
        # 关闭Redis连接
        from app.core.redis_client import close_redis_client
        await close_redis_client()
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("Redis连接关闭时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭Redis连接时出现错误: {e}")

    try:
        # 检查是否启用 Telegram
        telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
        if telegram_enabled:
            from app.core.auto_bot import stop_bot, send_telegram_message, bot_initialized, has_bot_lock
            # 只有持有锁的进程才发送关闭消息和停止 Bot
            if bot_initialized and has_bot_lock():
                # 尝试发送关闭消息（可能失败，因为连接可能已断开）
                try:
                    await asyncio.wait_for(
                        send_telegram_message(f"🧩 服务 [{settings.SERVER_NAME}] 已关闭"),
                        timeout=3.0
                    )
                except asyncio.CancelledError:
                    # 应用关闭时任务被取消是正常的
                    logger.debug("发送关闭消息时任务被取消（正常关闭流程）")
                except asyncio.TimeoutError:
                    logger.debug(f"发送关闭消息超时（可能连接已断开）")
                # 其他异常已在 send_telegram_message 内部处理，这里不需要捕获
                finally:
                    stop_bot()  # stop_bot 内部会检查是否持有锁并释放
            else:
                # 其他进程不需要执行任何操作
                if bot_initialized:
                    logger.debug(f"[PID:{os.getpid()}] 未持有 Bot 锁，跳过关闭操作")
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("关闭 Telegram 机器人时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭 Telegram 机器人时出现错误: {e}")

    try:
        # 清理数据库连接池
        await engine.dispose()
        logger.info("数据库连接池已关闭")
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("关闭数据库连接池时任务被取消（正常关闭流程）")
    except Exception as e:
        # 关闭时的错误不应该影响应用关闭流程
        logger.warning(f"关闭数据库连接池时出现错误: {e}")
    finally:
        logger.info("应用已关闭")

    


# 初始化FastAPI应用
# 生产环境禁用API文档
app = FastAPI(
    title=settings.SERVER_NAME,
    description=settings.SERVER_DESCRIPTION,
    version="1.0.0",
    docs_url=None if settings.is_production else f"{settings.API_V1_STR}/docs",
    redoc_url=None if settings.is_production else f"{settings.API_V1_STR}/redoc",
    openapi_url=None if settings.is_production else f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan  # 使用 lifespan 替代已弃用的 @app.on_event()
)

# ====== 添加安全中间件 ======
# 注意：中间件的添加顺序很重要，后添加的中间件会先执行

# 1. HTTPS强制重定向中间件（最外层，生产环境强制HTTPS）
if settings.is_production:
    app.add_middleware(HTTPSRedirectMiddleware)

# 2. 性能监控中间件（记录慢请求）
app.add_middleware(PerformanceMonitoringMiddleware)

# 3. 请求日志中间件（记录所有请求）
app.add_middleware(RequestLoggingMiddleware)

# 4. 响应压缩中间件（减少网络传输量，特别适用于移动端）
# 注意：如果 Nginx 已配置 gzip 压缩，可以禁用此中间件以提高性能
# 暂时禁用，由 Nginx 处理压缩（更高效）
# app.add_middleware(CompressionMiddleware)

# 5. CSRF防护中间件（防止CSRF攻击）
if settings.ENABLE_CSRF:
    from app.core.csrf import CSRFMiddleware
    app.add_middleware(CSRFMiddleware)
    logger.info("CSRF防护已启用")

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
            "X-Frame-Options"
        ],  # 暴露的响应头
        max_age=3600,  # 预检请求缓存时间（1小时）
    )


# ====== 全局异常处理 ======
# 注意：FastAPI 会自动处理 HTTPException，不需要单独注册处理器
# 但我们可以为特定异常类型添加自定义处理

def _make_json_serializable(obj):
    """
    递归地将对象转换为JSON可序列化的格式
    处理bytes、datetime等不可序列化的类型
    """
    if isinstance(obj, bytes):
        # 将bytes转换为base64编码的字符串
        try:
            # 尝试解码为UTF-8字符串
            return obj.decode('utf-8', errors='replace')
        except:
            # 如果无法解码，返回base64编码
            return base64.b64encode(obj).decode('utf-8')
    elif isinstance(obj, dict):
        return {key: _make_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_json_serializable(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        # 处理对象
        return _make_json_serializable(obj.__dict__)
    else:
        # 其他类型直接返回（JSON可以处理的基本类型）
        return obj


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    处理请求验证错误
    统一返回标准格式，不暴露敏感信息
    业务错误返回200状态码，通过响应体中的code字段表示错误
    """
    # 获取错误信息并转换为JSON可序列化格式
    errors = exc.errors()
    serializable_errors = _make_json_serializable(errors)

    # 尝试提取第一个错误的详细信息
    error_detail = "请检查请求参数格式"
    if errors and len(errors) > 0:
        first_error = errors[0]
        loc = first_error.get("loc", [])
        msg = first_error.get("msg", "")
        if loc:
            field_name = loc[-1]
            error_detail = f"参数 '{field_name}' 错误: {msg}"
        else:
            error_detail = f"参数错误: {msg}"

    logger.warning(f"请求验证失败: {request.url.path} | 错误: {serializable_errors}")
    error_response = create_error_response(
        error_code=ErrorCode.VALIDATION_ERROR,
        message="请求参数验证失败",
        detail=error_detail,
        data={"errors": serializable_errors}
    )
    # 业务错误返回200状态码，通过响应体中的code字段表示错误
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=error_response,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    处理 HTTPException
    统一返回标准格式
    
    设计原则：
    - 如果 detail 已经是标准格式（字典，包含 code 字段），说明是业务错误，返回200状态码
    - 如果 status_code 是 500 或 503，说明是服务器错误，保持原状态码
    - 其他情况（401等特殊状态码除外），业务错误返回200状态码
    
    Args:
        request: 请求对象
        exc: HTTPException 异常对象
    """
    # 如果 detail 已经是标准格式（字典，包含 code 字段），说明是通过 raise_api_exception 抛出的
    # 此时应该使用 exc.status_code（已经在 raise_api_exception 中正确设置）
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        # 业务错误应该返回200，只有真正的服务器错误才返回500
        # 但如果是401（未授权），需要保持401状态码以便浏览器处理
        response_status_code = exc.status_code
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            # 401 未授权：保持401状态码，浏览器会自动处理
            response_status_code = status.HTTP_401_UNAUTHORIZED
        elif exc.status_code in (status.HTTP_500_INTERNAL_SERVER_ERROR, status.HTTP_503_SERVICE_UNAVAILABLE):
            # 500/503 服务器错误：保持原状态码
            response_status_code = exc.status_code
        else:
            # 其他业务错误：返回200状态码，通过响应体中的code字段表示错误
            response_status_code = status.HTTP_200_OK

        # 检查连接是否仍然有效
        try:
            if hasattr(request, '_is_disconnected') and request._is_disconnected:
                logger.debug("客户端已断开连接，跳过HTTPException响应")
                from anyio import EndOfStream
                raise EndOfStream("客户端已断开连接")
        except Exception:
            pass
        
        # 记录严重的 HTTPException (500/503) 到审计日志
        if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            from app.core.errors import record_http_exception_log
            await record_http_exception_log(exc, request, "HTTPException")

        # 尝试返回响应，但如果连接已断开，捕获异常
        try:
            # 再次检查连接状态（在返回响应前）
            # 如果连接已断开，直接抛出流异常，不尝试创建响应
            try:
                if hasattr(request, '_is_disconnected') and request._is_disconnected:
                    logger.debug("客户端已断开连接，无法发送HTTPException响应")
                    from anyio import EndOfStream
                    raise EndOfStream("客户端已断开连接")
            except EndOfStream:
                # 如果已经是流异常，直接重新抛出
                raise
            except (ConnectionError, OSError, RuntimeError) as conn_err:
                error_type = type(conn_err).__name__
                error_module = type(conn_err).__module__
                if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                    "anyio" in error_module):
                    raise
            except Exception:
                pass
            
            # 检查是否有CSRF token需要添加到响应头
            try:
                response = JSONResponse(
                    status_code=response_status_code,
                    content=exc.detail,
                )
                
                # 如果HTTPException中包含了新的CSRF token，添加到响应头
                if hasattr(exc, '_csrf_token') and exc._csrf_token:
                    try:
                        response.headers["X-CSRF-Token"] = exc._csrf_token
                        logger.debug("已在403错误响应中添加正确的CSRF token（供前端自动更新）")
                    except Exception:
                        pass
                
                return response
            except (ConnectionError, OSError, RuntimeError) as create_error:
                # 在创建响应时捕获流异常
                error_type = type(create_error).__name__
                error_module = type(create_error).__module__
                if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                    "anyio" in error_module):
                    logger.debug("连接已断开，无法创建HTTPException响应")
                    raise create_error
                raise
        except (ConnectionError, OSError, RuntimeError) as stream_error:
            error_type = type(stream_error).__name__
            error_module = type(stream_error).__module__
            if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                "anyio" in error_module):
                logger.debug("连接已断开，无法发送HTTPException响应")
                raise stream_error
            raise

    # 否则，从 HTTPException 的 detail 中提取错误信息
    # 这种情况通常是直接使用 HTTPException 抛出的（应该避免，应使用 raise_api_exception）
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

    # 根据状态码映射到错误码
    status_to_error_code = {
        status.HTTP_400_BAD_REQUEST: ErrorCode.BAD_REQUEST,
        status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
        status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
        status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
        status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY: ErrorCode.VALIDATION_ERROR,
        status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.TOO_MANY_REQUESTS,
        status.HTTP_500_INTERNAL_SERVER_ERROR: ErrorCode.INTERNAL_ERROR,
        status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
    }

    error_code = status_to_error_code.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

    error_response = create_error_response(
        error_code=error_code,
        message=detail,
        detail=detail
    )

    # 业务错误返回200，只有真正的服务器错误才返回500
    # 但是 401 和 403 需要保持原状态码，以便前端正确处理
    response_status_code = exc.status_code
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        # 401 未授权：保持401状态码
        response_status_code = status.HTTP_401_UNAUTHORIZED
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        # 403 禁止访问：保持403状态码（如客户被禁用、用户被禁用等）
        # 这样前端可以通过状态码直接判断错误类型，避免将错误响应误判为成功响应
        response_status_code = status.HTTP_403_FORBIDDEN
    elif exc.status_code in (status.HTTP_500_INTERNAL_SERVER_ERROR, status.HTTP_503_SERVICE_UNAVAILABLE):
        # 500/503 服务器错误：保持原状态码
        response_status_code = exc.status_code
    else:
        # 其他业务错误：返回200状态码
        response_status_code = status.HTTP_200_OK

    # 检查连接是否仍然有效（避免在连接断开时尝试发送响应）
    try:
        if hasattr(request, '_is_disconnected') and request._is_disconnected:
            logger.debug("客户端已断开连接，跳过HTTPException响应")
            # 连接已断开，重新抛出流异常，让ASGI服务器处理
            from anyio import EndOfStream
            raise EndOfStream("客户端已断开连接")
    except Exception:
        pass
    
    # 记录严重的 HTTPException (500/503) 到审计日志
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        from app.core.errors import record_http_exception_log
        await record_http_exception_log(exc, request, "HTTPException")

    # 尝试返回响应，但如果连接已断开，捕获异常
    try:
        # 再次检查连接状态（在创建响应前）
        # 如果连接已断开，直接抛出流异常，不尝试创建响应
        try:
            if hasattr(request, '_is_disconnected') and request._is_disconnected:
                logger.debug("客户端已断开连接，无法发送HTTPException响应")
                from anyio import EndOfStream
                raise EndOfStream("客户端已断开连接")
        except EndOfStream:
            # 如果已经是流异常，直接重新抛出
            raise
        except (ConnectionError, OSError, RuntimeError) as conn_err:
            error_type = type(conn_err).__name__
            error_module = type(conn_err).__module__
            if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                "anyio" in error_module):
                raise
        except Exception:
            pass
        
        # 检查是否有CSRF token需要添加到响应头（服务器重启后自动生成新token）
        try:
            response = JSONResponse(
                status_code=response_status_code,
                content=error_response,
            )
            
            # 如果HTTPException中包含了新的CSRF token（令牌不匹配时返回正确的令牌），添加到响应头
            if hasattr(exc, '_csrf_token') and exc._csrf_token:
                try:
                    response.headers["X-CSRF-Token"] = exc._csrf_token
                    logger.debug("已在403错误响应中添加正确的CSRF token（供前端自动更新）")
                except Exception:
                    pass
            
            return response
        except (ConnectionError, OSError, RuntimeError) as create_error:
            # 在创建响应时捕获流异常
            error_type = type(create_error).__name__
            error_module = type(create_error).__module__
            if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                "anyio" in error_module):
                logger.debug("连接已断开，无法创建HTTPException响应")
                raise create_error
            raise
    except (ConnectionError, OSError, RuntimeError) as stream_error:
        # 检查是否是流关闭异常
        error_type = type(stream_error).__name__
        error_module = type(stream_error).__module__
        if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
            "anyio" in error_module):
            logger.debug("连接已断开，无法发送HTTPException响应")
            # 连接已断开，重新抛出流异常，让ASGI服务器处理
            raise stream_error
        # 其他连接错误，重新抛出
        raise


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理器
    捕获所有未处理的异常（不包括 HTTPException），防止泄露敏感信息
    
    注意：
    - HTTPException 会被上面的处理器处理，不会到达这里
    - 只有真正的程序代码错误（未捕获的异常）才会到达这里，返回500状态码
    - 流关闭异常（EndOfStream, WouldBlock）直接重新抛出，不记录错误
    
    Args:
        request: 请求对象
        exc: 异常对象
    """
    # HTTPException 应该由专门的处理器处理，不应该到达这里
    # 但如果到达这里，说明可能在异常处理过程中连接已断开
    if isinstance(exc, HTTPException):
        # 首先检查是否是流关闭异常（可能在异常链中）
        error_type = type(exc).__name__
        error_module = type(exc).__module__
        if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
            "anyio" in error_module):
            # 如果HTTPException本身就是流异常包装的，直接重新抛出
            raise exc
        
        # 检查连接是否已断开
        # 如果连接已断开，不应该尝试发送响应，直接抛出流异常
        try:
            # 检查请求的连接状态
            if hasattr(request, '_is_disconnected') and request._is_disconnected:
                logger.debug("客户端已断开连接，跳过HTTPException处理")
                # 连接已断开，直接抛出流异常，让ASGI服务器处理
                from anyio import EndOfStream
                raise EndOfStream("客户端已断开连接")
        except EndOfStream:
            # 如果已经是流异常，直接重新抛出
            raise
        except Exception:
            pass
        
        # 尝试检查连接状态（通过检查异常上下文）
        # 如果HTTPException是在连接断开时抛出的，其上下文可能包含流异常信息
        if hasattr(exc, '__context__') and exc.__context__:
            context_exc = exc.__context__
            context_type = type(context_exc).__name__
            context_module = type(context_exc).__module__
            if ("EndOfStream" in context_type or "WouldBlock" in context_type or 
                "anyio" in context_module):
                logger.debug("检测到连接断开上下文，跳过HTTPException处理")
                # 直接重新抛出原始的流异常，而不是创建新的
                raise context_exc
        
        # 如果连接仍然有效，重新抛出 HTTPException 让专门的处理器处理
        # 但如果重新抛出时连接断开，会被下面的流异常检查捕获
        try:
            raise exc
        except (ConnectionError, OSError, RuntimeError) as stream_error:
            # 检查是否是流关闭异常
            error_type = type(stream_error).__name__
            error_module = type(stream_error).__module__
            if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                "anyio" in error_module):
                logger.debug("连接已断开，无法发送HTTPException响应")
                # 连接已断开，直接重新抛出流异常，让ASGI服务器处理
                raise stream_error
            # 其他连接错误，重新抛出
            raise
        except Exception as e:
            # 如果重新抛出时捕获到其他异常，检查是否是流异常
            error_type = type(e).__name__
            error_module = type(e).__module__
            if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
                "anyio" in error_module):
                logger.debug("检测到流异常，跳过HTTPException处理")
                raise e
            # 其他异常，重新抛出
            raise

    # 检查是否是流关闭相关的异常（客户端提前关闭连接）
    error_type = type(exc).__name__
    error_module = type(exc).__module__
    if ("EndOfStream" in error_type or "WouldBlock" in error_type or 
        "anyio" in error_module):
        # 流关闭异常是正常的（客户端提前关闭连接），不需要记录错误
        # 直接重新抛出，让 ASGI 服务器处理
        raise exc

    # 记录详细的错误信息（包括堆栈跟踪）
    error_message = str(exc)
    logger.error(
        f"未处理的异常: {request.url.path} | 错误类型: {error_type} | 错误: {error_message}",
        exc_info=True
    )

    # 记录运行错误到审计日志（异步执行，不阻塞错误响应）
    try:
        from app.core.audit_log import log_runtime_error
        from app.core.database import AsyncSessionLocal
        import traceback
        import asyncio

        # 异步记录错误日志，不阻塞错误响应
        async def record_error_log():
            audit_db = None
            try:
                audit_db = AsyncSessionLocal()

                # 尝试从请求中获取当前用户（如果有认证信息）
                current_user = None
                username = None
                try:
                    from app.core.security import JWTUtils
                    from app.models.models import User
                    from sqlalchemy.future import select

                    token = request.headers.get("Authorization", "").replace("Bearer ", "")
                    if token:
                        payload = await JWTUtils.verify_token(token)
                        if payload and "sub" in payload:
                            user_id = payload.get("sub")
                            if user_id:
                                try:
                                    user_id_int = int(user_id)
                                    result = await audit_db.execute(select(User).where(User.id == user_id_int))
                                    current_user = result.scalar_one_or_none()
                                    if current_user:
                                        username = current_user.username
                                except (ValueError, Exception):
                                    pass
                except Exception:
                    # 如果无法获取用户，继续使用 None
                    pass

                # 限制错误信息长度
                max_error_length = 1000
                truncated_error = error_message[:max_error_length] if len(
                    error_message) > max_error_length else error_message

                # 获取堆栈跟踪（限制长度）
                stack_trace = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                max_stack_length = 2000
                truncated_stack = stack_trace[:max_stack_length] if len(stack_trace) > max_stack_length else stack_trace

                await log_runtime_error(
                    db=audit_db,
                    error_type=error_type,
                    error_message=truncated_error,
                    request=request,
                    user=current_user,
                    username=username,
                    resource_type="SYSTEM",
                    resource_name=request.url.path,
                    details={
                        "path": request.url.path,
                        "method": request.method,
                        "stack_trace": truncated_stack
                    }
                )
                await audit_db.commit()
            except Exception as log_error:
                # 日志记录失败不应该影响错误处理
                logger.warning(f"记录运行错误日志失败: {log_error}")
            finally:
                if audit_db:
                    try:
                        await audit_db.close()
                    except Exception:
                        pass

        # 在后台任务中记录日志，不阻塞错误响应
        asyncio.create_task(record_error_log())
    except Exception as e:
        # 如果导入或记录日志失败，不影响错误处理
        logger.warning(f"记录运行错误日志时发生异常: {e}")

    # 生产环境不返回详细错误信息，避免泄露敏感信息
    error_detail = "服务器内部错误，请稍后重试"
    if not settings.is_production:
        # 开发环境可以返回详细错误信息，便于调试
        error_detail = f"服务器内部错误: {str(exc)}"

    error_response = create_error_response(
        error_code=ErrorCode.INTERNAL_ERROR,
        message=error_detail,
        detail=error_detail
    )

    # 这是真正的程序代码错误，返回500状态码
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response,
    )


# 根路由健康检查
@app.get("/")
async def root():
    return {
        "status": "success",
        "message": f"{settings.SERVER_NAME} is running",
        "version": "1.0.0"
    }


# 包含API路由
app.include_router(api_router, prefix=settings.API_V1_STR)

# 短链接重定向路由（公开访问，无需认证）
# 注意：这个路由必须在 API 路由之后注册，避免与 API 路由冲突
from fastapi import Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timezone
from typing import Optional
from app.core.database import get_db
from app.models.models import ShortLink

@app.get("/s/{short_code}", summary="短链接重定向", tags=["短链接服务"])
async def redirect_short_link_public(
    short_code: str,
    offer_id: Optional[int] = Query(None, description="Offer ID（从URL参数获取）"),
    channel_id: Optional[int] = Query(None, description="渠道ID（从URL参数获取）"),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """
    短链接重定向（公开接口，无需认证）
    高并发优化：使用Redis缓存减少数据库查询，异步更新点击次数
    
    支持查询参数传递：
    - 如果访问短链接时带有查询参数，这些参数会被合并到真实URL中
    - 例如：/s/abc123?param1=value1 会重定向到 original_url?param1=value1
    """
    from app.core.short_link_cache import (
        get_short_link_from_cache, 
        set_short_link_to_cache,
        serialize_short_link
    )
    from app.core.short_link_click_counter import increment_click_count_async
    from app.core.tracking.click_id_generator import generate_click_id_from_timestamp
    from app.api.api_v1.endpoints.tracking import create_click_background
    from app.models.models import Click
    from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
    
    def merge_url_params(base_url: str, query_params: dict) -> str:
        """
        将查询参数合并到基础URL中
        如果基础URL已有参数，则合并；如果没有，则添加
        新参数会覆盖基础URL中的同名参数
        注意：click_id 参数会始终放在最前面
        """
        if not query_params:
            return base_url
        
        # 解析基础URL
        parsed = urlparse(base_url)
        
        # 解析基础URL中已有的查询参数
        existing_params = parse_qs(parsed.query, keep_blank_values=True)
        
        # 分离 click_id 和其他参数
        click_id_value = None
        other_params = {}
        
        for key, value in query_params.items():
            if key == 'click_id':
                # 保存 click_id 的值
                if isinstance(value, list):
                    click_id_value = [str(v) for v in value]
                else:
                    click_id_value = [str(value)]
            else:
                # 其他参数
                if isinstance(value, list):
                    other_params[key] = [str(v) for v in value]
                else:
                    other_params[key] = [str(value)]
        
        # 合并参数：先合并其他参数，再添加 click_id（确保 click_id 在最前面）
        for key, value in other_params.items():
            existing_params[key] = value
        
        # 如果有 click_id，将其放在最前面
        if click_id_value:
            existing_params['click_id'] = click_id_value
        
        # 重新构建查询字符串（使用 OrderedDict 确保 click_id 在最前面）
        from collections import OrderedDict
        ordered_params = OrderedDict()
        
        # 先添加 click_id（如果存在）
        if 'click_id' in existing_params:
            ordered_params['click_id'] = existing_params['click_id']
        
        # 然后添加其他参数
        for key, value in existing_params.items():
            if key != 'click_id':
                ordered_params[key] = value
        
        new_query = urlencode(ordered_params, doseq=True)
        
        # 重新构建URL
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)
    
    try:
        # 记录请求详细信息（用于调试）
        request_url = str(request.url)
        request_params = dict(request.query_params)
        logger.info(
            f"[短链接重定向] 收到请求: short_code={short_code}, "
            f"完整URL={request_url}, 查询参数={request_params}"
        )
        
        # ====== 第一步：尝试从缓存获取 ======
        cached_data = await get_short_link_from_cache(short_code)
        
        if cached_data:
            # 缓存命中，直接使用缓存数据
            original_url = cached_data["original_url"]
            is_active = cached_data["is_active"]
            expires_at_str = cached_data.get("expires_at")
            
            # 检查是否激活
            if not is_active:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="短链接已禁用"
                )
            
            # 检查是否过期
            if expires_at_str:
                # 解析ISO格式的日期时间字符串
                try:
                    expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    else:
                        expires_at = expires_at.astimezone(timezone.utc)
                except (ValueError, AttributeError):
                    # 如果解析失败，从数据库重新查询
                    expires_at = None
                
                now = datetime.now(timezone.utc)
                if expires_at < now:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="短链接已过期"
                    )
            
            # 验证URL格式
            if not original_url or not original_url.startswith(('http://', 'https://')):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="短链接配置错误：原始URL格式无效"
                )
            
            # 生成点击值（UUID风格的click_id）
            click_id = generate_click_id_from_timestamp()
            
            # 获取短链接ID（从缓存中获取，如果没有则从数据库查询）
            short_link_id = cached_data.get("id")
            if not short_link_id:
                try:
                    result = await db.execute(
                        select(ShortLink.id).where(ShortLink.short_code == short_code)
                    )
                    short_link_id = result.scalar()
                except Exception:
                    short_link_id = None
            
            # 获取客户端信息
            def get_client_ip(req: Request) -> Optional[str]:
                """获取客户端真实IP"""
                if not req:
                    return None
                forwarded_for = req.headers.get("X-Forwarded-For")
                if forwarded_for:
                    return forwarded_for.split(",")[0].strip()
                real_ip = req.headers.get("X-Real-IP")
                if real_ip:
                    return real_ip
                if req.client:
                    return req.client.host
                return None
            
            client_ip = get_client_ip(request)
            user_agent = request.headers.get("user-agent")
            referer = request.headers.get("referer")
            
            # 只使用URL参数中的offer_id和channel_id（如果有的话）
            # 如果URL参数中没有，则不保存这些值
            final_offer_id = offer_id  # 只使用URL参数
            final_channel_id = channel_id  # 只使用URL参数
            
            # 如果从URL参数获取了offer_id，尝试从缓存获取advertiser_id（高并发优化）
            advertiser_id = None
            if final_offer_id:
                # 优先从缓存获取（减少数据库查询）
                from app.core.offer_cache import get_offer_advertiser_id
                advertiser_id = await get_offer_advertiser_id(final_offer_id)
                
                # 如果缓存中没有，查询数据库并缓存
                if advertiser_id is None:
                    try:
                        from app.models.models import Offer
                        offer_result = await db.execute(
                            select(Offer).where(Offer.id == final_offer_id)
                        )
                        offer = offer_result.scalars().first()
                        if offer:
                            advertiser_id = offer.advertiser_id
                            # 缓存Offer信息
                            from app.core.offer_cache import set_offer_cache
                            await set_offer_cache(final_offer_id, advertiser_id, offer.offer_name)
                    except Exception as e:
                        logger.warning(f"查询Offer失败: offer_id={final_offer_id}, error={e}")
            
            # 打印获得的参数
            logger.info(
                f"[短链接点击-缓存路径] 参数信息: "
                f"short_code={short_code}, "
                f"URL参数_offer_id={offer_id}, "
                f"URL参数_channel_id={channel_id}, "
                f"最终保存_offer_id={final_offer_id}, "
                f"最终保存_channel_id={final_channel_id}, "
                f"advertiser_id={advertiser_id}"
            )
            
            # 创建点击记录（使用Redis队列，高并发优化）
            if short_link_id:
                click_data = {
                    "click_id": click_id,
                    "short_link_id": short_link_id,
                    "offer_id": final_offer_id,  # 只保存URL参数中的值（如果有）
                    "publisher_id": final_channel_id,  # 只保存URL参数中的值（如果有），publisher_id对应channel_id
                    "advertiser_id": advertiser_id,  # 可能为None，批量处理时会补充
                    "click_time": datetime.now(timezone.utc).isoformat(),
                    "ip": client_ip,
                    "user_agent": user_agent,
                    "referer": referer,
                    "country": None
                }
                
                # 使用Redis队列缓冲（非阻塞，高并发优化）
                from app.core.clicks_queue import enqueue_click
                enqueued = await enqueue_click(click_data)
                
                if enqueued:
                    logger.debug(
                        f"[短链接重定向] 点击记录已加入队列（缓存路径）: "
                        f"click_id={click_id}, "
                        f"short_link_id={short_link_id}"
                    )
                else:
                    # 队列失败，降级到后台任务（兼容性）
                    logger.warning(f"Redis队列不可用，降级到后台任务: click_id={click_id}")
                    # 转换时间格式
                    click_data['click_time'] = datetime.now(timezone.utc)
                    background_tasks.add_task(create_click_background, click_data)
            
            # 获取当前点击次数（从缓存数据中获取，如果缓存中没有则从数据库查询）
            current_click_count = cached_data.get("click_count", 0)
            if not current_click_count:
                # 如果缓存中没有点击次数，从数据库查询
                try:
                    result = await db.execute(
                        select(ShortLink.click_count).where(ShortLink.short_code == short_code)
                    )
                    current_click_count = result.scalar() or 0
                except Exception:
                    current_click_count = 0
            
            # 异步更新点击次数（不阻塞重定向）
            try:
                await increment_click_count_async(short_code)
                # 获取Redis中的增量点击次数（用于日志记录）
                from app.core.redis_client import get_redis_client
                redis = await get_redis_client()
                redis_count = 0
                if redis:
                    try:
                        counter_key = f"short_link:click:{short_code}"
                        redis_count = await redis.get(counter_key)
                        redis_count = int(redis_count) if redis_count else 0
                    except Exception:
                        pass
                
                logger.info(
                    f"[短链接重定向] 点击计数已记录（缓存路径）: short_code={short_code}, "
                    f"click_id={click_id}, short_link_id={short_link_id}, 数据库点击次数={current_click_count}, Redis增量={redis_count}"
                )
            except Exception as e:
                logger.error(
                    f"[短链接重定向] 点击计数失败（缓存路径）: short_code={short_code}, click_id={click_id}, error={e}",
                    exc_info=True
                )
            
            # 将click_id添加到查询参数的最前面
            request_params_with_click = {'click_id': click_id}
            # 将原有参数添加到后面
            request_params_with_click.update(request_params)
            
            # 合并查询参数到原始URL（包含click_id，click_id在最前面）
            final_url = merge_url_params(original_url, request_params_with_click)
            logger.debug(f"[短链接重定向] 重定向到: {final_url}")
            
            # 直接重定向（最快路径）
            return RedirectResponse(url=final_url, status_code=302)
        
        # ====== 第二步：缓存未命中，查询数据库 ======
        result = await db.execute(
            select(ShortLink).where(ShortLink.short_code == short_code)
        )
        short_link = result.scalars().first()
        
        if not short_link:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"短链接不存在: {short_code}"
            )
        
        # 检查是否激活
        if not short_link.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="短链接已禁用"
            )
        
        # 检查是否过期
        if short_link.expires_at:
            expires_at = short_link.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            else:
                expires_at = expires_at.astimezone(timezone.utc)
            
            now = datetime.now(timezone.utc)
            if expires_at < now:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="短链接已过期"
                )
        
        # 验证原始URL格式
        original_url = short_link.original_url
        if not original_url or not original_url.startswith(('http://', 'https://')):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="短链接配置错误：原始URL格式无效"
            )
        
        # 写入缓存（供后续请求使用）
        await set_short_link_to_cache(short_code, serialize_short_link(short_link))
        
        # 生成点击值（UUID风格的click_id）
        click_id = generate_click_id_from_timestamp()
        
        # 获取客户端信息
        def get_client_ip(req: Request) -> Optional[str]:
            """获取客户端真实IP"""
            if not req:
                return None
            forwarded_for = req.headers.get("X-Forwarded-For")
            if forwarded_for:
                return forwarded_for.split(",")[0].strip()
            real_ip = req.headers.get("X-Real-IP")
            if real_ip:
                return real_ip
            if req.client:
                return req.client.host
            return None
        
        client_ip = get_client_ip(request)
        user_agent = request.headers.get("user-agent")
        referer = request.headers.get("referer")
        
        # 只使用URL参数中的offer_id和channel_id（如果有的话）
        # 如果URL参数中没有，则不保存这些值
        final_offer_id = offer_id  # 只使用URL参数
        final_channel_id = channel_id  # 只使用URL参数
        
        # 如果从URL参数获取了offer_id，尝试从缓存获取advertiser_id（高并发优化）
        advertiser_id = None
        if final_offer_id:
            # 优先从缓存获取（减少数据库查询）
            from app.core.offer_cache import get_offer_advertiser_id
            advertiser_id = await get_offer_advertiser_id(final_offer_id)
            
            # 如果缓存中没有，查询数据库并缓存
            if advertiser_id is None:
                try:
                    from app.models.models import Offer
                    offer_result = await db.execute(
                        select(Offer).where(Offer.id == final_offer_id)
                    )
                    offer = offer_result.scalars().first()
                    if offer:
                        advertiser_id = offer.advertiser_id
                        # 缓存Offer信息
                        from app.core.offer_cache import set_offer_cache
                        await set_offer_cache(final_offer_id, advertiser_id, offer.offer_name)
                except Exception as e:
                    logger.warning(f"查询Offer失败: offer_id={final_offer_id}, error={e}")
        
        # 打印获得的参数
        logger.info(
            f"[短链接点击-数据库路径] 参数信息: "
            f"short_code={short_code}, "
            f"URL参数_offer_id={offer_id}, "
            f"URL参数_channel_id={channel_id}, "
            f"最终保存_offer_id={final_offer_id}, "
            f"最终保存_channel_id={final_channel_id}, "
            f"advertiser_id={advertiser_id}"
        )
        
        # 创建点击记录（使用Redis队列，高并发优化）
        click_data = {
            "click_id": click_id,
            "short_link_id": short_link.id,
            "offer_id": final_offer_id,
            "publisher_id": final_channel_id,  # publisher_id对应channel_id
            "advertiser_id": advertiser_id,  # 可能为None，批量处理时会补充
            "click_time": datetime.now(timezone.utc).isoformat(),
            "ip": client_ip,
            "user_agent": user_agent,
            "referer": referer,
            "country": None
        }
        
        # 使用Redis队列缓冲（非阻塞，高并发优化）
        from app.core.clicks_queue import enqueue_click
        enqueued = await enqueue_click(click_data)
        
        if enqueued:
            logger.debug(
                f"[短链接重定向] 点击记录已加入队列（数据库路径）: "
                f"click_id={click_id}, "
                f"short_link_id={short_link.id}"
            )
        else:
            # 队列失败，降级到后台任务（兼容性）
            logger.warning(f"Redis队列不可用，降级到后台任务: click_id={click_id}")
            # 转换时间格式
            click_data['click_time'] = datetime.now(timezone.utc)
            background_tasks.add_task(create_click_background, click_data)
        
        # 获取当前点击次数（数据库中的点击次数）
        current_click_count = short_link.click_count or 0
        
        # 异步更新点击次数（不阻塞重定向）
        try:
            await increment_click_count_async(short_code)
            # 获取Redis中的增量点击次数（用于日志记录）
            from app.core.redis_client import get_redis_client
            redis = await get_redis_client()
            redis_count = 0
            if redis:
                try:
                    counter_key = f"short_link:click:{short_code}"
                    redis_count = await redis.get(counter_key)
                    redis_count = int(redis_count) if redis_count else 0
                except Exception:
                    pass
            
            logger.info(
                f"[短链接重定向] 点击计数已记录（数据库路径）: short_code={short_code}, "
                f"click_id={click_id}, short_link_id={short_link.id}, 数据库点击次数={current_click_count}, Redis增量={redis_count}"
            )
        except Exception as e:
            logger.error(
                f"[短链接重定向] 点击计数失败（数据库路径）: short_code={short_code}, click_id={click_id}, error={e}",
                exc_info=True
            )
        
        # 将click_id添加到查询参数的最前面
        request_params_with_click = {'click_id': click_id}
        # 将原有参数添加到后面
        request_params_with_click.update(request_params)
        
        # 合并查询参数到原始URL（包含click_id，click_id在最前面）
        final_url = merge_url_params(original_url, request_params_with_click)
        logger.debug(f"[短链接重定向] 重定向到: {final_url}")
        
        # 执行重定向
        return RedirectResponse(url=final_url, status_code=302)
        
    except HTTPException as http_exc:
        # 记录HTTP异常（404等）
        logger.warning(
            f"[短链接重定向] HTTP异常: short_code={short_code}, "
            f"完整URL={str(request.url) if 'request' in locals() else 'N/A'}, "
            f"状态码={http_exc.status_code}, 详情={http_exc.detail}"
        )
        # 重新抛出 HTTP 异常
        raise
    except Exception as e:
        # 记录所有其他异常
        request_url = str(request.url) if 'request' in locals() else 'N/A'
        logger.error(
            f"[短链接重定向] 处理异常: short_code={short_code}, "
            f"完整URL={request_url}, "
            f"查询参数={request_params if 'request_params' in locals() else 'N/A'}, "
            f"error={str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"短链接重定向失败: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8960,
        reload=True,
        log_level="info",
        access_log=False  # 禁用 uvicorn 的默认访问日志，使用我们的 RequestLoggingMiddleware（支持中文路径解码）
    )
