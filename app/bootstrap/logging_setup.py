"""
应用日志初始化。

须在导入其他 app 子模块前调用 ``configure_logging()``，保证 logger 配置一致。
"""
import io
import logging
import os
import sys
import tempfile
import warnings

from app.core.config import settings
from app.core.constants import LOG_DIR_MODE, LOG_FILE_BACKUP_COUNT, LOG_FILE_MAX_BYTES
from app.core.log_filters import PostbackLoggerFilter
from app.core.log_handlers import SafeRotatingFileHandler

warnings.filterwarnings('ignore', message='.*pkg_resources is deprecated.*', category=UserWarning)




def configure_logging() -> logging.Logger:
    """配置根日志与各分类 handler，返回 main 模块 logger。"""
    _setup_logging()
    return logging.getLogger("app.main")


def get_logger(name: str = "app.main") -> logging.Logger:
    return logging.getLogger(name)


def _setup_logging() -> None:
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
            """绑定目标 logger 与写入级别（stdout 默认 INFO）。"""
            self.logger = logger
            self.log_level = log_level

        def write(self, message):
            """将 print 输出逐行写入日志，自动加 [STDOUT] 前缀。"""
            if message and message.strip():  # 忽略空行
                # 移除换行符，logger 会自动添加
                message = message.rstrip('\n\r')
                if message:
                    # 避免重复输出：检查消息是否已经包含日志格式
                    if not message.startswith('[STDOUT]') and not message.startswith('[STDERR]'):
                        self.logger.log(self.log_level, f"[STDOUT] {message}")

        def flush(self):
            """兼容 file-like 接口，无缓冲无需刷新。"""
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
            """返回 False 时丢弃含 EndOfStream 的 uvicorn/anyio 断连日志。"""
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
