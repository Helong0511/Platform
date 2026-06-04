"""
FastAPI应用主入口
配置应用、中间件、路由、异常处理等
"""
import asyncio
import base64
import logging
import os
import sys
import tempfile
import traceback
import warnings
from contextlib import asynccontextmanager
from app.core.log_filters import PostbackLoggerFilter
from app.core.log_handlers import SafeRotatingFileHandler

from anyio import EndOfStream
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.future import select

from app.api_v1 import api_router
from app.core.audit_log import log_runtime_error
from app.core.cache_manager import CacheManager
from app.core.config import settings
# ====== 常量定义 ======
# 从常量模块导入，避免魔法数字
from app.core.constants import (
    LOG_FILE_MAX_BYTES,
    LOG_FILE_BACKUP_COUNT,
    LOG_DIR_MODE,
    MAX_ERROR_MESSAGE_LENGTH,
    MAX_STACK_TRACE_LENGTH
)
from app.core.csrf import CSRFMiddleware
from app.core.database import AsyncSessionLocal, engine, init_db
from app.core.errors import ErrorCode, create_error_response, record_http_exception_log
from app.core.https_middleware import HTTPSRedirectMiddleware
from app.core.middleware import (
    PerformanceMonitoringMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    SensitivePathGuardMiddleware,
)
from app.core.redis_client import get_redis_client, close_redis_client
from app.core.security import JWTUtils
# 从新模块导入 Bot 相关函数（统一使用新模块）
from app.core.telegram.file_lock import is_lock_held as has_bot_lock
from app.core.telegram.file_lock import release_bot_lock as stop_bot
from app.core.telegram.polling_manager import start_bot_thread
from app.core.telegram.service_notify import (
    notify_service_started,
    notify_service_stopped,
    should_run_telegram_polling,
)
from app.core.telegram.shared_state import cleanup_stale_shared_state
from app.core.timezone_utils import check_and_validate_timezone, log_timezone_info
from app.core.utils import get_client_ip
from app.models.models import Base, User
from app.scheduler_module import (
    init_scheduled_tasks, start_scheduler, shutdown_scheduler
)
from app.scheduler_module.task_init import init_scheduled_tasks_in_db

# 抑制 APScheduler 的 pkg_resources 弃用警告
# 这是 APScheduler 库内部使用已弃用的 pkg_resources 导致的警告
# 不影响功能，等待库更新修复
warnings.filterwarnings('ignore', message='.*pkg_resources is deprecated.*', category=UserWarning)


# ====== 辅助函数 ======
def _get_log_directory() -> str:
    """获取日志目录路径，如果无法创建则使用临时目录"""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    try:
        os.makedirs(log_dir, exist_ok=True, mode=LOG_DIR_MODE)
        # 尝试设置目录权限（如果可能）
        try:
            os.chmod(log_dir, LOG_DIR_MODE)
        except (OSError, PermissionError):
            pass  # 如果没有权限设置，继续执行
        return log_dir
    except (OSError, PermissionError) as e:
        # 如果无法创建日志目录，使用临时目录
        log_dir = tempfile.gettempdir()
        logging.warning(f"无法创建日志目录，使用临时目录: {log_dir}, 错误: {e}")
        return log_dir


def _create_console_handler(formatter: logging.Formatter, level: int = logging.INFO) -> logging.StreamHandler:
    """创建控制台日志处理器"""
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler


# 确保日志目录存在并设置权限
log_dir = _get_log_directory()

# ====== 配置根日志记录器 ======
# 这样所有子模块的日志都会被记录
root_logger = logging.getLogger()
# 生产环境使用WARNING级别，开发环境使用INFO级别
# 但允许通过环境变量 LOG_LEVEL 覆盖
log_level = settings.LOG_LEVEL if hasattr(settings, 'LOG_LEVEL') else ("WARNING" if settings.is_production else "INFO")
root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

# 多进程环境优化：在日志中包含进程ID、线程ID、模块名等详细信息
formatter = logging.Formatter(
    '%(asctime)s - [PID:%(process)d] - [TID:%(thread)d] - %(name)s - %(levelname)s - %(message)s'
)

# 详细格式化器，包含更多上下文信息
detailed_formatter = logging.Formatter(
    '%(asctime)s - [PID:%(process)d] - [TID:%(thread)d] - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
)

# ====== 创建分类日志文件 ======
# 1. app.log: 只记录 WARNING 及以上级别（重要日志）
app_log_handler = None
app_log_path = os.path.join(log_dir, 'app.log')
try:
    app_log_handler = SafeRotatingFileHandler(
        app_log_path,
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding='utf-8'
    )
    app_log_handler.setFormatter(detailed_formatter)
    app_log_handler.setLevel(logging.WARNING)  # 只记录 WARNING 及以上级别
    root_logger.addHandler(app_log_handler)
except (OSError, PermissionError) as e:
    root_logger.warning(f"无法创建 app.log 文件: {e}")

# 2. scheduler.log: 记录调度器相关的详细日志（INFO级别）
scheduler_log_handler = None
scheduler_log_path = os.path.join(log_dir, 'scheduler.log')
try:
    scheduler_log_handler = SafeRotatingFileHandler(
        scheduler_log_path,
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding='utf-8'
    )
    scheduler_log_handler.setFormatter(detailed_formatter)
    _scheduler_file_level = logging.INFO if settings.is_production else logging.DEBUG
    scheduler_log_handler.setLevel(_scheduler_file_level)

    # 只添加到调度器相关的 logger
    # 注意：propagate=True，这样 WARNING 及以上级别会同时输出到 app.log
    scheduler_logger = logging.getLogger('app.scheduler')
    scheduler_logger.addHandler(scheduler_log_handler)
    scheduler_logger.setLevel(_scheduler_file_level)
    scheduler_logger.propagate = True  # 允许传播，WARNING+ 会输出到 app.log

    # 调度器模块的 logger
    scheduler_module_logger = logging.getLogger('app.scheduler_module')
    scheduler_module_logger.addHandler(scheduler_log_handler)
    scheduler_module_logger.setLevel(_scheduler_file_level)
    scheduler_module_logger.propagate = True  # 允许传播，WARNING+ 会输出到 app.log
except (OSError, PermissionError) as e:
    root_logger.warning(f"无法创建 scheduler.log 文件: {e}")

# 3. telegram.log: 记录 Telegram Bot 相关的详细日志（INFO级别）
telegram_log_handler = None
telegram_log_path = os.path.join(log_dir, 'telegram.log')
try:
    telegram_log_handler = SafeRotatingFileHandler(
        telegram_log_path,
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding='utf-8'
    )
    telegram_log_handler.setFormatter(detailed_formatter)
    telegram_log_handler.setLevel(logging.DEBUG)  # 记录 DEBUG 及以上级别，更详细

    # 只添加到 Telegram 相关的 logger
    # 注意：propagate=True，这样 WARNING 及以上级别会同时输出到 app.log
    telegram_logger = logging.getLogger('app.core.telegram')
    telegram_logger.addHandler(telegram_log_handler)
    telegram_logger.setLevel(logging.DEBUG)
    telegram_logger.propagate = True  # 允许传播，WARNING+ 会输出到 app.log
except (OSError, PermissionError) as e:
    root_logger.warning(f"无法创建 telegram.log 文件: {e}")

# 4. postback.log: 记录 PostBack 处理相关的详细日志（INFO级别）
postback_log_handler = None
postback_log_path = os.path.join(log_dir, 'postback.log')
try:
    postback_log_handler = SafeRotatingFileHandler(
        postback_log_path,
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding='utf-8'
    )
    postback_log_handler.setFormatter(detailed_formatter)
    _postback_file_level = logging.INFO if settings.is_production else logging.DEBUG
    postback_log_handler.setLevel(_postback_file_level)
    postback_log_handler.addFilter(PostbackLoggerFilter())

    # PostBack：子 logger 向上传播，父节点挂 handler + Filter 即可覆盖 postback 相关模块
    for _postback_parent in ('app.core.postback', 'app.services.cpl'):
        _pb_logger = logging.getLogger(_postback_parent)
        _pb_logger.addHandler(postback_log_handler)
        _pb_logger.setLevel(_postback_file_level)
        _pb_logger.propagate = True
except (OSError, PermissionError) as e:
    root_logger.warning(f"无法创建 postback.log 文件: {e}")

# 5. debug.log: 记录 DEBUG 级别日志（仅开发环境）
debug_log_handler = None
if not settings.is_production:
    debug_log_path = os.path.join(log_dir, 'debug.log')
    try:
        debug_log_handler = SafeRotatingFileHandler(
            debug_log_path,
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUP_COUNT,
            encoding='utf-8'
        )
        debug_log_handler.setFormatter(detailed_formatter)
        debug_log_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(debug_log_handler)
    except (OSError, PermissionError) as e:
        root_logger.warning(f"无法创建 debug.log 文件: {e}")

# 6. access.log: 记录所有HTTP请求的详细日志
access_log_handler = None
access_log_path = os.path.join(log_dir, 'access.log')
try:
    access_log_handler = SafeRotatingFileHandler(
        access_log_path,
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding='utf-8'
    )
    access_log_handler.setFormatter(detailed_formatter)
    access_log_handler.setLevel(logging.INFO)
    # 创建专门的访问日志记录器
    access_logger = logging.getLogger('access')
    access_logger.addHandler(access_log_handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False  # 不传播，避免重复记录
except (OSError, PermissionError) as e:
    root_logger.warning(f"无法创建 access.log 文件: {e}")

# 向后兼容：file_handler 指向 app_log_handler（用于 stdout/stderr 重定向）
file_handler = app_log_handler

# 记录日志文件创建信息
if app_log_handler:
    log_files_info = [
        "app.log (WARNING+)",
        "scheduler.log (DEBUG+)",
        "telegram.log (DEBUG+)",
        "postback.log (DEBUG+)",
        "access.log (INFO+)",
        "debug.log (DEBUG+, 仅开发环境)"
    ]
    root_logger.warning(f"日志文件已创建: {', '.join(log_files_info)}")


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
                # 避免重复输出：检查消息是否已经包含日志格式
                if not message.startswith('[STDOUT]') and not message.startswith('[STDERR]'):
                    self.logger.log(self.log_level, f"[STDOUT] {message}")

    def flush(self):
        pass


# 创建专门的 logger 用于捕获 stdout/stderr
# stdout/stderr 输出到 debug.log（开发环境，INFO+）或 app.log（生产环境，WARNING+）
stdout_logger = logging.getLogger('stdout')
stdout_logger.setLevel(logging.INFO)
# stdout 输出到 debug.log（开发环境）或 app.log（生产环境，WARNING+）
if debug_log_handler:
    stdout_logger.addHandler(debug_log_handler)
elif app_log_handler:
    stdout_logger.addHandler(app_log_handler)
else:
    stdout_logger.addHandler(_create_console_handler(formatter, logging.INFO))
stdout_logger.propagate = False  # 防止重复输出

stderr_logger = logging.getLogger('stderr')
stderr_logger.setLevel(logging.WARNING)
# stderr 输出到 app.log（WARNING+）
if app_log_handler:
    stderr_logger.addHandler(app_log_handler)
else:
    stderr_logger.addHandler(_create_console_handler(formatter, logging.WARNING))
stderr_logger.propagate = False  # 防止重复输出

# 重定向 stdout 和 stderr（生产环境也重定向，确保 print() 输出被记录）
sys.stdout = LoggingStream(stdout_logger, logging.INFO)
sys.stderr = LoggingStream(stderr_logger, logging.WARNING)

# 防止日志重复输出（如果已经有handler，不添加console handler）
if not root_logger.handlers or not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
    # 开发环境也输出到控制台
    if not settings.is_production:
        root_logger.addHandler(_create_console_handler(formatter, logging.INFO))

# ====== 精简调度器相关日志 ======
# 将APScheduler的日志级别设置为WARNING，减少"Running job"等详细日志
# 这些日志会输出到 scheduler.log（如果配置了），WARNING+ 会同时输出到 app.log
apscheduler_logger = logging.getLogger('apscheduler')
apscheduler_logger.setLevel(logging.WARNING)
if scheduler_log_handler:
    apscheduler_logger.addHandler(scheduler_log_handler)
    apscheduler_logger.propagate = True  # WARNING+ 会传播到 root logger（app.log）

apscheduler_executor_logger = logging.getLogger('apscheduler.executors.default')
apscheduler_executor_logger.setLevel(logging.WARNING)
if scheduler_log_handler:
    apscheduler_executor_logger.addHandler(scheduler_log_handler)
    apscheduler_executor_logger.propagate = True

apscheduler_scheduler_logger = logging.getLogger('apscheduler.schedulers')
apscheduler_scheduler_logger.setLevel(logging.WARNING)
if scheduler_log_handler:
    apscheduler_scheduler_logger.addHandler(scheduler_log_handler)
    apscheduler_scheduler_logger.propagate = True

# 调度器模块的详细日志输出到 scheduler.log
# 这些模块的 INFO 级别日志会输出到 scheduler.log
# WARNING 及以上级别会同时输出到 app.log（因为 propagate=True）
if scheduler_log_handler:
    # process_allocator, task_queue, lock 的详细日志输出到 scheduler.log
    for module_name in ['app.scheduler_module.process_allocator',
                        'app.scheduler_module.task_queue',
                        'app.scheduler_module.lock',
                        'app.scheduler_module.scheduler']:
        module_logger = logging.getLogger(module_name)
        module_logger.addHandler(scheduler_log_handler)
        module_logger.setLevel(logging.INFO)  # 允许 INFO 级别输出到 scheduler.log
        module_logger.propagate = True  # WARNING+ 会传播到 root logger（app.log）


# ====== 配置 uvicorn 日志过滤器 ======
# 过滤掉 EndOfStream 异常，这些是客户端提前关闭连接的正常情况，不应该记录为错误
class StreamErrorFilter(logging.Filter):
    """
    日志过滤器，过滤掉流关闭异常（EndOfStream）
    这些异常通常表示客户端提前关闭了连接，是正常情况，不应该记录为错误
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # 检查日志消息中是否包含 EndOfStream
        if hasattr(record, 'msg') and record.msg:
            msg = str(record.msg)
            if 'EndOfStream' in msg or 'anyio.EndOfStream' in msg:
                return False  # 过滤掉
        # 检查异常信息
        if hasattr(record, 'exc_info') and record.exc_info:
            exc_type, exc_value, exc_traceback = record.exc_info
            if exc_type and exc_value:
                exc_name = exc_type.__name__
                exc_module = exc_type.__module__
                if 'EndOfStream' in exc_name or 'anyio' in exc_module:
                    return False  # 过滤掉
        # 检查堆栈跟踪文本（uvicorn 会将异常信息记录在消息中）
        if hasattr(record, 'getMessage'):
            try:
                message = record.getMessage()
                if 'EndOfStream' in message or 'anyio.EndOfStream' in message:
                    return False  # 过滤掉
            except Exception:
                pass
        return True  # 允许其他日志通过


# 将过滤器添加到 uvicorn 和 uvicorn.error 日志记录器
uvicorn_logger = logging.getLogger('uvicorn')
uvicorn_logger.addFilter(StreamErrorFilter())
uvicorn_error_logger = logging.getLogger('uvicorn.error')
uvicorn_error_logger.addFilter(StreamErrorFilter())
# 同时添加到 gunicorn 的错误日志记录器（如果使用 gunicorn）
gunicorn_error_logger = logging.getLogger('gunicorn.error')
gunicorn_error_logger.addFilter(StreamErrorFilter())

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

    try:
        from app.core.tracking.click_persist import log_click_persist_mode_at_startup

        log_click_persist_mode_at_startup()
    except Exception as e:
        logger.debug("点击落库策略日志跳过: %s", e)

    # 确保数据库存在并创建表（多进程环境：每个 worker 都会执行，但数据库操作是安全的）
    try:
        from app.db.database import create_database

        # 创建数据库（如果不存在）
        await create_database()

        # 创建所有表（如果不存在，使用 IF NOT EXISTS 语义）
        # 导入所有模型以确保SQLAlchemy能够发现所有表
        from app.models import (
            User, Client, Product, AdData, ProductAssignment,
            ScheduledTask, UserAuditLog, UserSession, TokenBlacklist,
            PostbackConversion, PendingPostbackConversion, PostbackIpWhitelist
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info(f"[Worker PID:{worker_pid}] 数据库表创建完成")
    except Exception as e:
        # 检查是否是 MySQL 并发 DDL 错误（错误代码 1684）
        # 这个错误表示表正在被其他进程修改，可以安全忽略
        is_concurrent_ddl_error = False
        error_code = None

        # 尝试从异常中提取错误代码
        try:
            if hasattr(e, 'orig'):
                # SQLAlchemy 包装的异常 (sqlalchemy.exc.OperationalError)
                orig = e.orig
                if hasattr(orig, 'args') and len(orig.args) > 0:
                    error_code = orig.args[0] if isinstance(orig.args[0], int) else None
            elif hasattr(e, 'args') and len(e.args) > 0:
                # 直接 pymysql 异常
                error_code = e.args[0] if isinstance(e.args[0], int) else None

            # 检查错误代码或错误消息
            if error_code == 1684 or (str(e) and '1684' in str(e)):
                is_concurrent_ddl_error = True
        except Exception:
            # 如果提取错误代码失败，检查错误消息
            error_str = str(e)
            if '1684' in error_str or 'concurrent DDL' in error_str.lower():
                is_concurrent_ddl_error = True

        if is_concurrent_ddl_error:
            # 这是预期的并发行为，降级为信息级别
            logger.info(
                f"[Worker PID:{worker_pid}] 检测到并发 DDL 操作（表可能正在被其他 worker 创建），"
                f"这是正常的多进程环境行为，继续启动..."
            )
        else:
            # 其他错误，记录为错误级别
            logger.error(f"[Worker PID:{worker_pid}] 数据库表创建失败: {e}", exc_info=True)
            # 不抛出异常，允许应用继续启动（可能是表已存在或其他 worker 已创建）
            logger.warning(f"[Worker PID:{worker_pid}] 继续启动应用...")

    # 初始化数据库，创建默认管理员账户
    try:
        await init_db()
        logger.info(f"[Worker PID:{worker_pid}] 数据库初始化完成（包括默认管理员账户）")
    except Exception as e:
        logger.error(f"[Worker PID:{worker_pid}] 数据库初始化失败: {e}", exc_info=True)
        # 不抛出异常，允许应用继续启动

    # 初始化Redis连接（如果配置了）
    try:
        redis_client = await get_redis_client()
        if redis_client:
            logger.info(f"[Worker PID:{worker_pid}] Redis连接已初始化")
        else:
            logger.info(f"[Worker PID:{worker_pid}] Redis未配置，使用内存存储")
    except Exception as e:
        logger.warning(f"[Worker PID:{worker_pid}] Redis初始化失败: {e}，将使用内存存储")

    # 定时任务：仅调度 worker 启动（Gunicorn 多 worker 时由 SCHEDULER_WORKER=1 标识）
    if settings.should_run_scheduler():
        try:
            logger.info(f"[Worker PID:{worker_pid}] 开始初始化定时任务...")

            try:
                await init_scheduled_tasks_in_db()
            except Exception as db_init_error:
                logger.warning(
                    f"[Worker PID:{worker_pid}] 初始化任务到数据库失败: {db_init_error}，继续启动..."
                )

            await init_scheduled_tasks()
            logger.info(f"[Worker PID:{worker_pid}] 定时任务初始化完成，正在启动调度器...")
            await start_scheduler()
            logger.info(f"[Worker PID:{worker_pid}] 定时任务调度器已启动")
        except Exception as e:
            logger.error(f"[Worker PID:{worker_pid}] 定时任务初始化失败: {e}", exc_info=True)
            logger.warning(f"[Worker PID:{worker_pid}] 应用将继续启动，但定时任务功能可能不可用")
    else:
        logger.info(
            f"[Worker PID:{worker_pid}] 跳过定时任务调度器"
            f"（ENABLE_SCHEDULER/SCHEDULER_WORKER 未启用本 worker）"
        )

    # Telegram：调度进程只发启停通知；API 进程才启动 Bot 轮询（单实例文件锁）
    try:
        cleanup_stale_shared_state()
        telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
        logger.info(
            f"[Worker PID:{worker_pid}] Telegram 启用={telegram_enabled}, "
            f"轮询={should_run_telegram_polling()}"
        )
        if not telegram_enabled:
            logger.info(f"[Worker PID:{worker_pid}] Telegram 已禁用，跳过")
        elif should_run_telegram_polling():
            from app.core.telegram.bot_initializer import initialize_bot
            from app.core.telegram import bot_state

            logger.info(f"[Worker PID:{worker_pid}] 初始化 Telegram Bot（API 进程）...")
            bot_instance, initialized, available = initialize_bot()
            logger.info(
                f"[Worker PID:{worker_pid}] Bot 初始化: initialized={initialized}, available={available}"
            )
            bot_initialized = bot_state.bot_initialized

            if initialized and bot_initialized:
                start_success = start_bot_thread()
                if not start_success:
                    logger.info(
                        f"[Worker PID:{worker_pid}] Bot 轮询未启动（其他进程已占用或未取得锁）"
                    )
            else:
                logger.info(f"[Worker PID:{worker_pid}] Bot 未配置或初始化失败，跳过轮询")
        else:
            logger.info(
                f"[Worker PID:{worker_pid}] 调度进程不启动 Bot 轮询，仅发送服务启停通知"
            )
    except Exception as e:
        logger.error(f"[Worker PID:{worker_pid}] Telegram 初始化失败: {e}", exc_info=True)
        logger.warning(f"[Worker PID:{worker_pid}] 应用将继续启动，Telegram 可能不可用")

    # 缓存预热（可选，在后台异步执行，不阻塞启动）
    try:
        # 在后台任务中执行缓存预热，不阻塞应用启动
        async def warmup_cache_background():
            try:
                async with AsyncSessionLocal() as db:
                    await CacheManager.warmup_all(db)
            except Exception as e:
                logger.warning(f"缓存预热失败: {e}，不影响应用启动")

        # 延迟执行缓存预热，确保数据库和Redis都已初始化
        asyncio.create_task(warmup_cache_background())
        logger.info(f"[Worker PID:{worker_pid}] 缓存预热任务已启动（后台执行）")
    except Exception as e:
        logger.warning(f"[Worker PID:{worker_pid}] 启动缓存预热失败: {e}，继续启动...")

    logger.info("应用启动完成")

    # 按 systemd 服务角色发送启动通知（与 Bot 锁无关）
    try:
        if notify_service_started():
            logger.info(f"[Worker PID:{worker_pid}] 已发送服务启动 Telegram 通知")
        else:
            logger.debug(f"[Worker PID:{worker_pid}] 未发送服务启动通知（非通知 worker 或已禁用）")
    except Exception as e:
        logger.warning(f"发送服务启动通知失败: {e}", exc_info=True)

    # ====== 应用运行期间 ======
    yield

    # ====== 关闭时执行 ======
    logger.info("应用关闭中...")
    try:
        if settings.should_run_scheduler():
            await shutdown_scheduler()
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("定时任务调度器关闭时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭定时任务调度器时出现错误: {e}")

    try:
        # 关闭Redis连接
        await close_redis_client()
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("Redis连接关闭时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭Redis连接时出现错误: {e}")

    try:
        telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
        if telegram_enabled:
            try:
                notify_service_stopped()
            except asyncio.CancelledError:
                logger.debug("发送服务关闭通知时任务被取消（正常关闭流程）")
            except asyncio.TimeoutError:
                logger.debug("发送服务关闭通知超时（可能连接已断开）")
            from app.core.telegram import bot_state as _bot_state_mod
            if (
                should_run_telegram_polling()
                and _bot_state_mod.bot_initialized
                and has_bot_lock()
            ):
                try:
                    stop_bot()
                except Exception as stop_err:
                    logger.warning(f"释放 Telegram Bot 锁时出错: {stop_err}")
            elif should_run_telegram_polling() and _bot_state_mod.bot_initialized:
                logger.debug(f"[PID:{os.getpid()}] 未持有 Bot 锁，跳过 stop_bot")
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


# ====== 初始化FastAPI应用 ======
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

# 0. 流异常处理中间件（最外层，静默处理客户端提前关闭连接的异常）
from app.core.middleware import StreamErrorHandlingMiddleware

app.add_middleware(StreamErrorHandlingMiddleware)

# 0.5 敏感路径防护（防 .env / wp-admin 等扫描；生产环境屏蔽文档路径探测）
if settings.ENABLE_SENSITIVE_PATH_GUARD:
    app.add_middleware(SensitivePathGuardMiddleware)

# 1. HTTPS强制重定向中间件（生产环境强制HTTPS）
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
            "X-Frame-Options",
            "X-CSRF-Token"  # 暴露CSRF令牌响应头
        ],  # 暴露的响应头
        max_age=3600,  # 预检请求缓存时间（1小时）
    )


# ====== 全局异常处理 ======
# 注意：FastAPI 会自动处理 HTTPException，不需要单独注册处理器
# 但我们可以为特定异常类型添加自定义处理

def _is_stream_error(exc: Exception) -> bool:
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


def _check_connection_disconnected(request: Request) -> bool:
    """
    检查请求连接是否已断开
    
    Args:
        request: 请求对象
    
    Returns:
        如果连接已断开返回True，否则返回False
    """
    return hasattr(request, '_is_disconnected') and request._is_disconnected


def _raise_stream_error_if_disconnected(request: Request) -> None:
    """
    如果连接已断开，抛出流异常
    
    Args:
        request: 请求对象
    
    Raises:
        EndOfStream: 如果连接已断开
    """
    if _check_connection_disconnected(request):
        logger.debug("客户端已断开连接")
        raise EndOfStream("客户端已断开连接")


def _determine_response_status_code(exc_status_code: int) -> int:
    """
    根据异常状态码确定响应状态码
    
    业务错误返回200，只有真正的服务器错误才返回500
    但是 401 和 403 需要保持原状态码，以便前端正确处理
    
    Args:
        exc_status_code: 异常状态码
    
    Returns:
        响应状态码
    """
    if exc_status_code == status.HTTP_401_UNAUTHORIZED:
        return status.HTTP_401_UNAUTHORIZED
    elif exc_status_code == status.HTTP_403_FORBIDDEN:
        return status.HTTP_403_FORBIDDEN
    elif exc_status_code in (status.HTTP_500_INTERNAL_SERVER_ERROR, status.HTTP_503_SERVICE_UNAVAILABLE):
        return exc_status_code
    else:
        return status.HTTP_200_OK


def _add_csrf_token_to_response(response: JSONResponse, exc: HTTPException) -> None:
    """
    如果HTTPException中包含了新的CSRF token，添加到响应头
    
    Args:
        response: JSONResponse对象
        exc: HTTPException异常对象
    """
    if hasattr(exc, '_csrf_token') and exc._csrf_token:
        try:
            response.headers["X-CSRF-Token"] = exc._csrf_token
            logger.debug("已在错误响应中添加正确的CSRF token（供前端自动更新）")
        except Exception:
            pass


async def _create_http_exception_response(
        request: Request,
        exc: HTTPException,
        content: dict | str,
        response_status_code: int
) -> JSONResponse:
    """
    创建HTTPException响应，处理连接检查和CSRF token
    
    Args:
        request: 请求对象
        exc: HTTPException异常对象
        content: 响应内容（字典或字符串）
        response_status_code: 响应状态码
    
    Returns:
        JSONResponse对象
    
    Raises:
        EndOfStream: 如果连接已断开
    """
    # 检查连接是否仍然有效
    try:
        _raise_stream_error_if_disconnected(request)
    except Exception:
        pass

    # 记录严重的 HTTPException (500/503) 到审计日志
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        await record_http_exception_log(exc, request, "HTTPException")

    # 尝试返回响应，但如果连接已断开，捕获异常
    try:
        # 再次检查连接状态（在返回响应前）
        _raise_stream_error_if_disconnected(request)

        # 创建响应
        response = JSONResponse(
            status_code=response_status_code,
            content=content,
        )

        # 添加CSRF token（如果存在）
        _add_csrf_token_to_response(response, exc)

        return response
    except Exception as e:
        # 如果是流异常，直接重新抛出
        if _is_stream_error(e):
            logger.debug("连接已断开，无法发送HTTPException响应")
            raise
        # 其他异常，重新抛出
        raise


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
        except (UnicodeDecodeError, AttributeError):
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


def _client_api_validation_hint(path: str, errors: list) -> str | None:
    """客户开放 API 常见校验失败的可读说明。"""
    if "/client_data" not in path and "/client_products" not in path:
        return None
    for err in errors:
        loc = err.get("loc") or ()
        if err.get("type") == "missing" and "req_time" in loc:
            return (
                "缺少必填参数 req_time（10 位 Unix 秒级时间戳，如 int(time.time())）。"
                "签名须按字母序拼接 client_id、data_type、end_date、req_time、start_date"
                "（仅非空字段）后追加 &key=客户密钥，再 MD5 小写。"
            )
        if err.get("type") == "missing" and "sign" in loc:
            return "缺少必填参数 sign（MD5 签名，须与 req_time 等参数一并参与计算）。"
    if any(err.get("type") == "json_invalid" for err in errors):
        return (
            "请求体不是合法 JSON，请设置 Content-Type: application/json，"
            "并检查 JSON 语法（如逗号、引号、括号是否匹配）。"
        )
    return None


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

    path = request.url.path
    error_detail = _client_api_validation_hint(path, errors) or "请检查请求参数格式"
    if error_detail == "请检查请求参数格式" and errors:
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
        data={"errors": serializable_errors},
        path=request.url.path
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
    # 首先检查异常上下文是否是流异常（连接已断开）
    # 如果是，直接重新抛出流异常，让 ASGI 服务器处理
    # 注意：不要在这里抛出，而是让异常自然传播，避免被 global_exception_handler 捕获后再次抛出
    if hasattr(exc, '__context__') and exc.__context__:
        context_exc = exc.__context__
        if _is_stream_error(context_exc):
            logger.debug("HTTPException的上下文是流异常，连接已断开，跳过响应创建")
            # 直接重新抛出流异常，让 ASGI 服务器处理
            # 使用 from None 避免创建新的异常链，防止被 global_exception_handler 捕获
            raise context_exc from None

    # 检查连接是否已断开（使用非阻塞方式）
    # 注意：这里不能尝试读取流，只能检查标记
    try:
        if _check_connection_disconnected(request):
            logger.debug("检测到连接已断开，跳过HTTPException响应创建")
            raise EndOfStream("客户端已断开连接")
    except Exception as stream_exc:
        # 如果检测到连接断开，抛出流异常
        if _is_stream_error(stream_exc):
            logger.debug("检测到连接已断开，跳过HTTPException响应创建")
            raise stream_exc
        # 其他异常，忽略（继续处理HTTPException）

    # 如果 detail 已经是标准格式（字典，包含 code 字段），说明是通过 raise_api_exception 抛出的
    # 此时应该使用 exc.status_code（已经在 raise_api_exception 中正确设置）
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        response_status_code = _determine_response_status_code(exc.status_code)
        return await _create_http_exception_response(request, exc, exc.detail, response_status_code)

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
        detail=detail,
        path=request.url.path
    )

    # 业务错误返回200，只有真正的服务器错误才返回500
    # 但是 401 和 403 需要保持原状态码，以便前端正确处理
    response_status_code = _determine_response_status_code(exc.status_code)
    return await _create_http_exception_response(request, exc, error_response, response_status_code)


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
        # 检查是否是流关闭异常
        if _is_stream_error(exc):
            # 直接重新抛出，让 ASGI 服务器处理
            raise exc

        # 尝试检查连接状态（通过检查异常上下文）
        # 如果异常上下文是流异常，说明连接已断开，直接重新抛出流异常
        # 注意：如果流异常是从 http_exception_handler 传播过来的，应该直接让它继续传播
        # 检查异常链中是否有流异常（包括 __context__ 和 __cause__）
        context_exc = None
        if hasattr(exc, '__context__') and exc.__context__:
            if _is_stream_error(exc.__context__):
                context_exc = exc.__context__
        if not context_exc and hasattr(exc, '__cause__') and exc.__cause__:
            if _is_stream_error(exc.__cause__):
                context_exc = exc.__cause__

        if context_exc:
            logger.debug("检测到连接断开上下文，跳过HTTPException处理")
            # 直接重新抛出流异常，让 ASGI 服务器处理
            # 使用 from None 避免创建新的异常链，防止被再次捕获
            raise context_exc from None

        # 检查连接是否已断开（使用非阻塞方式）
        # 注意：这里不能尝试读取流，只能检查标记
        try:
            if _check_connection_disconnected(request):
                logger.debug("检测到连接已断开，跳过HTTPException处理")
                raise EndOfStream("客户端已断开连接")
        except Exception as stream_exc:
            # 如果检测到连接断开，抛出流异常
            if _is_stream_error(stream_exc):
                logger.debug("检测到连接已断开，跳过HTTPException处理")
                raise stream_exc
            # 其他异常，忽略（继续处理HTTPException）

        # 如果连接仍然有效，重新抛出 HTTPException 让专门的处理器处理
        # HTTPException 应该由 http_exception_handler 处理，不应该到达这里
        # 如果到达这里，可能是异常处理顺序问题，直接重新抛出让上层处理
        raise exc

    # 检查是否是流关闭相关的异常（客户端提前关闭连接）
    if _is_stream_error(exc):
        # 流关闭异常是正常的（客户端提前关闭连接），不需要记录错误
        # 直接重新抛出，让 ASGI 服务器处理
        raise exc

    # 记录详细的错误信息（包括堆栈跟踪）
    # 注意：RequestLoggingMiddleware 已经记录了简要异常信息，这里记录完整堆栈跟踪
    error_message = str(exc)
    error_type = type(exc).__name__
    try:
        client_ip = get_client_ip(request)
    except Exception:
        client_ip = "unknown"
    
    logger.error(
        f"未处理的异常: {request.method} {request.url.path} | 错误类型: {error_type} | 错误: {error_message} | IP: {client_ip}",
        exc_info=True
    )

    # 记录运行错误到审计日志（异步执行，不阻塞错误响应）
    try:
        # 异步记录错误日志，不阻塞错误响应
        async def record_error_log():
            audit_db = None
            try:
                audit_db = AsyncSessionLocal()

                # 尝试从请求中获取当前用户（如果有认证信息）
                current_user = None
                username = None
                try:

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
                truncated_error = (
                    error_message[:MAX_ERROR_MESSAGE_LENGTH]
                    if len(error_message) > MAX_ERROR_MESSAGE_LENGTH
                    else error_message
                )

                # 获取堆栈跟踪（限制长度）
                stack_trace = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                truncated_stack = (
                    stack_trace[:MAX_STACK_TRACE_LENGTH]
                    if len(stack_trace) > MAX_STACK_TRACE_LENGTH
                    else stack_trace
                )

                # 收集详细的请求信息
                request_details = {
                    "path": request.url.path,
                    "method": request.method,
                    "stack_trace": truncated_stack,
                    "query_params": str(request.query_params) if request.query_params else None,
                    "client_ip": None,
                    "user_agent": request.headers.get("User-Agent", None)
                }

                # 获取客户端IP
                try:
                    request_details["client_ip"] = get_client_ip(request)
                except Exception:
                    pass

                await log_runtime_error(
                    db=audit_db,
                    error_type=error_type,
                    error_message=truncated_error,
                    request=request,
                    user=current_user,
                    username=username,
                    resource_type="SYSTEM",
                    resource_name=request.url.path,
                    details=request_details
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
        logger.warning(f"记录运行错误日志时发生异常: {e}", exc_info=True)

    # 生产环境不返回详细错误信息，避免泄露敏感信息
    error_detail = "服务器内部错误，请稍后重试"
    if not settings.is_production:
        # 开发环境可以返回详细错误信息，便于调试
        error_detail = f"服务器内部错误: {str(exc)}"

    error_response = create_error_response(
        error_code=ErrorCode.INTERNAL_ERROR,
        message=error_detail,
        detail=error_detail,
        path=request.url.path
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

# 处理 favicon.ico 请求
@app.get("/favicon.ico")
async def favicon():
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
# 注意：这个路由必须在 API 路由之后注册，避免与 API 路由冲突
# 短链接重定向逻辑已重构为模块化结构：app/routes/short_link/
# 保持向后兼容：如果新模块不可用，回退到旧路由
try:
    from app.routes.short_link import router as short_link_redirect_router

    logger.info("使用模块化短链接路由（app/routes/short_link/）")
except ImportError:
    # 向后兼容：如果新模块不可用，使用旧路由
    from app.routes.short_link_redirect import router as short_link_redirect_router

    logger.warning("使用旧版短链接路由（向后兼容）")

app.include_router(short_link_redirect_router)

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
