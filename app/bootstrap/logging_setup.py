"""
应用日志初始化。

须在导入其他 app 子模块前调用 ``configure_logging()``，保证 logger 配置一致。
支持按级别拆分（error/warning/info）与按模块拆分；配置幂等可重复调用。

默认启用进程内 QueueHandler + QueueListener：业务线程只投递，文件 Handler
在后台线程落盘，降低请求路径磁盘阻塞。可通过 LOG_QUEUE_ENABLED=false 回退直写。
"""
import logging
import os
import sys
import tempfile
import threading
import warnings

from app.core.config import settings
from app.core.constants import LOG_DIR_MODE, LOG_FILE_BACKUP_COUNT, LOG_FILE_MAX_BYTES
from app.core.log_filters import (
    ErrorLogFormatter,
    LevelRangeFilter,
    LoggerNameExactFilter,
    LoggerNamePrefixFilter,
    LoggerNameRejectFilter,
    PostbackLoggerFilter,
    SensitiveDataFilter,
)
from app.core.log_handlers import SafeRotatingFileHandler, SafeStderrHandleErrorMixin, TelegramRuntimeErrorHandler
from app.core.log_queue import (
    is_log_queue_running,
    make_queue_handler,
    start_log_queue_listener,
    stop_log_queue_listener,
)

warnings.filterwarnings('ignore', message='.*pkg_resources is deprecated.*', category=UserWarning)


def _ensure_windows_utf8_stdio() -> None:
    """
    Windows 控制台默认多为 GBK(cp936)，而 Cursor/VS Code 终端按 UTF-8 捕获输出，
    会导致中文日志显示为「���」乱码。启动时统一切到 UTF-8。
    """
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_ensure_windows_utf8_stdio()

# 标记本模块创建的 Handler，便于幂等重建
_PLATFORM_HANDLER_ATTR = "_platform_log_handler"

# 重定向前保留真实标准流，供控制台 Handler 使用，避免「日志→stderr→LoggingStream→再记日志」回环
# 须在 UTF-8 重配置之后捕获，否则开发终端仍按 GBK 解码中文
_ORIGINAL_STDOUT = sys.stdout
_ORIGINAL_STDERR = sys.stderr

# EndOfStream 过滤（模块级类，避免每次 configure 生成新类导致 isinstance 失效、Filter 叠加）
class StreamErrorFilter(logging.Filter):
    """过滤 uvicorn/gunicorn 因客户端断连产生的 EndOfStream 噪音。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "msg") and record.msg:
            msg = str(record.msg)
            if "EndOfStream" in msg or "anyio.EndOfStream" in msg:
                return False
        if hasattr(record, "exc_info") and record.exc_info:
            exc_type, exc_value, _exc_traceback = record.exc_info
            if exc_type and exc_value and "EndOfStream" in exc_type.__name__:
                return False
        if hasattr(record, "getMessage"):
            try:
                message = record.getMessage()
                if "EndOfStream" in message or "anyio.EndOfStream" in message:
                    return False
            except Exception:
                pass
        return True


# 需要清理 Handler 的具名 logger
_MANAGED_LOGGER_NAMES = (
    "app.scheduler",
    "app.scheduler_module",
    "app.core.telegram",
    "app.core.postback",
    "app.services.cpl",
    "app.core.tracking",
    "app.api_v1.tracking",
    "app.services.tracking",
    "app.core.short_link",
    "app.routes.short_link",
    "app.api_v1.auth",
    "app.core.security",
    "access",
    "stdout",
    "stderr",
    "apscheduler",
    "apscheduler.executors.default",
    "apscheduler.schedulers",
)

_SCHEDULER_LOGGER_PREFIXES = (
    "app.scheduler",
    "app.scheduler_module",
    "apscheduler",
)
_TRACKING_LOGGER_PREFIXES = (
    "app.core.tracking",
    "app.api_v1.tracking",
    "app.services.tracking",
    "app.core.short_link",
    "app.routes.short_link",
)
_AUTH_LOGGER_PREFIXES = (
    "app.api_v1.auth",
    "app.core.security",
)
_POSTBACK_LOGGER_PREFIXES = (
    "app.core.postback",
    "app.services.cpl",
)


def configure_logging() -> logging.Logger:
    """配置根日志与各分类 handler，返回 main 模块 logger。"""
    _setup_logging()
    return logging.getLogger("app.main")


def get_logger(name: str = "app.main") -> logging.Logger:
    return logging.getLogger(name)


def _mark_handler(handler: logging.Handler) -> logging.Handler:
    setattr(handler, _PLATFORM_HANDLER_ATTR, True)
    return handler


def _is_platform_handler(handler: logging.Handler) -> bool:
    return bool(getattr(handler, _PLATFORM_HANDLER_ATTR, False))


def _detach_platform_handlers(logger: logging.Logger) -> list[logging.Handler]:
    """从 logger 卸下本应用 Handler，返回卸下的列表（不 close，避免共享 Handler 被重复关闭）。"""
    detached: list[logging.Handler] = []
    for handler in list(logger.handlers):
        if not _is_platform_handler(handler):
            continue
        logger.removeHandler(handler)
        detached.append(handler)
    return detached


def _close_handlers(handlers: list[logging.Handler]) -> None:
    seen: set[int] = set()
    for handler in handlers:
        hid = id(handler)
        if hid in seen:
            continue
        seen.add(hid)
        try:
            handler.close()
        except Exception:
            pass


def _rotation_params(*, for_error: bool = False) -> tuple[int, int]:
    """返回 (max_bytes, backup_count)，优先 settings。"""
    max_bytes = int(getattr(settings, "LOG_MAX_BYTES", None) or LOG_FILE_MAX_BYTES)
    if for_error:
        backup = int(
            getattr(settings, "LOG_ERROR_BACKUP_COUNT", None)
            or getattr(settings, "LOG_BACKUP_COUNT", None)
            or LOG_FILE_BACKUP_COUNT
        )
    else:
        backup = int(getattr(settings, "LOG_BACKUP_COUNT", None) or LOG_FILE_BACKUP_COUNT)
    return max(1024, max_bytes), max(1, backup)


def _create_rotating_handler(
    path: str,
    formatter: logging.Formatter,
    level: int,
    *,
    for_error: bool = False,
) -> SafeRotatingFileHandler:
    max_bytes, backup_count = _rotation_params(for_error=for_error)
    handler = SafeRotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    if for_error and not isinstance(formatter, ErrorLogFormatter):
        # 保证 error 文件使用带 [no_exc_info] 标记的格式器
        formatter = ErrorLogFormatter(formatter._fmt, datefmt=getattr(formatter, "datefmt", None))
    handler.setFormatter(formatter)
    handler.setLevel(level)
    if bool(getattr(settings, "LOG_SENSITIVE_FILTER_ENABLED", True)):
        handler.addFilter(SensitiveDataFilter())
    return _mark_handler(handler)


def _configure_named_loggers(names: tuple[str, ...] | list[str], level: int, *, propagate: bool) -> None:
    for name in names:
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.propagate = propagate


def _setup_logging() -> None:
    def _get_log_directory() -> str:
        """获取日志目录路径（项目根 ``logs/``，与 gunicorn.conf.py、.env LOG_FILE 一致）。"""
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        log_file = getattr(settings, "LOG_FILE", "logs/app.log")
        if os.path.isabs(log_file):
            log_dir = os.path.dirname(log_file)
        else:
            log_dir = os.path.join(project_root, os.path.dirname(log_file) or "logs")
        try:
            os.makedirs(log_dir, exist_ok=True, mode=LOG_DIR_MODE)
            try:
                os.chmod(log_dir, LOG_DIR_MODE)
            except (OSError, PermissionError):
                pass
            return log_dir
        except (OSError, PermissionError) as e:
            log_dir = tempfile.gettempdir()
            logging.warning(f"无法创建日志目录，使用临时目录: {log_dir}, 错误: {e}")
            return log_dir

    def _create_console_handler(formatter: logging.Formatter, level: int = logging.INFO) -> logging.StreamHandler:
        # 必须写到「真实 stderr」，不能写到已被 LoggingStream 劫持的 sys.stderr
        # Windows：确保流为 UTF-8，避免 Cursor 终端按 UTF-8 解读 GBK 字节导致乱码
        stream = _ORIGINAL_STDERR
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        class _ConsoleHandler(SafeStderrHandleErrorMixin, logging.StreamHandler):
            pass

        handler = _ConsoleHandler(stream)
        handler.setFormatter(formatter)
        handler.setLevel(level)
        if bool(getattr(settings, "LOG_SENSITIVE_FILTER_ENABLED", True)):
            handler.addFilter(SensitiveDataFilter())
        return _mark_handler(handler)

    use_queue = bool(getattr(settings, "LOG_QUEUE_ENABLED", True))
    log_dir = _get_log_directory()
    root_logger = logging.getLogger()

    # 幂等：先停 QueueListener（关闭其上文件 Handler），再卸下 logger 上的平台 Handler
    stop_log_queue_listener()
    _pending_close: list[logging.Handler] = []
    _pending_close.extend(_detach_platform_handlers(root_logger))
    for name in _MANAGED_LOGGER_NAMES:
        _pending_close.extend(_detach_platform_handlers(logging.getLogger(name)))
    _close_handlers(_pending_close)

    log_level = settings.LOG_LEVEL if hasattr(settings, "LOG_LEVEL") else (
        "WARNING" if settings.is_production else "INFO"
    )
    root_logger.setLevel(getattr(logging, str(log_level).upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s - [PID:%(process)d] - [TID:%(thread)d] - %(name)s - %(levelname)s - %(message)s"
    )
    detailed_formatter = logging.Formatter(
        "%(asctime)s - [PID:%(process)d] - [TID:%(thread)d] - %(name)s - %(levelname)s - "
        "%(funcName)s:%(lineno)d - %(message)s"
    )
    error_formatter = ErrorLogFormatter(
        "%(asctime)s - [PID:%(process)d] - [TID:%(thread)d] - %(name)s - %(levelname)s - "
        "%(funcName)s:%(lineno)d - %(message)s"
    )

    created_files: list[str] = []
    listener_handlers: list[logging.Handler] = []
    # 队列下 access 不传播到 root，但仍经同一 QueueListener；根级文件需拒绝 access
    _access_reject = LoggerNameRejectFilter(("access",))

    def _attach_root_file_handler(handler: logging.Handler) -> None:
        """根级分类文件：队列模式进 listener（并隔离 access）；直写挂 root。"""
        if use_queue:
            handler.addFilter(_access_reject)
            listener_handlers.append(handler)
            return
        root_logger.addHandler(handler)

    # 1. error.log：程序运行错误（ERROR+），含无栈 ERROR（标记 [no_exc_info]）
    error_log_handler = None
    if bool(getattr(settings, "LOG_ERROR_FILE_ENABLED", True)):
        try:
            error_log_handler = _create_rotating_handler(
                os.path.join(log_dir, "error.log"),
                error_formatter,
                logging.ERROR,
                for_error=True,
            )
            error_log_handler.addFilter(LevelRangeFilter(logging.ERROR, logging.CRITICAL))
            _attach_root_file_handler(error_log_handler)
            created_files.append("error.log (ERROR+)")
        except (OSError, PermissionError) as e:
            root_logger.warning(f"无法创建 error.log 文件: {e}")

    # 2. warning.log：仅 WARNING
    warning_log_handler = None
    if bool(getattr(settings, "LOG_WARNING_FILE_ENABLED", True)):
        try:
            warning_log_handler = _create_rotating_handler(
                os.path.join(log_dir, "warning.log"),
                detailed_formatter,
                logging.WARNING,
            )
            warning_log_handler.addFilter(LevelRangeFilter(logging.WARNING, logging.WARNING))
            _attach_root_file_handler(warning_log_handler)
            created_files.append("warning.log (WARNING)")
        except (OSError, PermissionError) as e:
            root_logger.warning(f"无法创建 warning.log 文件: {e}")

    # 3. app.log：WARNING+（兼容旧习惯，与 error/warning 有重叠）
    app_log_handler = None
    try:
        app_log_handler = _create_rotating_handler(
            os.path.join(log_dir, "app.log"),
            detailed_formatter,
            logging.WARNING,
        )
        _attach_root_file_handler(app_log_handler)
        created_files.append("app.log (WARNING+)")
    except (OSError, PermissionError) as e:
        root_logger.warning(f"无法创建 app.log 文件: {e}")

    # 4. info.log：可选，默认关
    info_log_handler = None
    if bool(getattr(settings, "LOG_INFO_FILE_ENABLED", False)):
        try:
            info_log_handler = _create_rotating_handler(
                os.path.join(log_dir, "info.log"),
                detailed_formatter,
                logging.INFO,
            )
            info_log_handler.addFilter(LevelRangeFilter(logging.INFO, logging.INFO))
            _attach_root_file_handler(info_log_handler)
            created_files.append("info.log (INFO)")
        except (OSError, PermissionError) as e:
            root_logger.warning(f"无法创建 info.log 文件: {e}")

    # 5. scheduler.log
    scheduler_log_handler = None
    _scheduler_file_level = logging.INFO if settings.is_production else logging.DEBUG
    try:
        scheduler_log_handler = _create_rotating_handler(
            os.path.join(log_dir, "scheduler.log"),
            detailed_formatter,
            _scheduler_file_level,
        )
        if use_queue:
            scheduler_log_handler.addFilter(LoggerNamePrefixFilter(_SCHEDULER_LOGGER_PREFIXES))
            listener_handlers.append(scheduler_log_handler)
        else:
            for _name in ("app.scheduler", "app.scheduler_module"):
                logging.getLogger(_name).addHandler(scheduler_log_handler)
        _configure_named_loggers(
            ("app.scheduler", "app.scheduler_module"),
            _scheduler_file_level,
            propagate=True,
        )
        created_files.append(f"scheduler.log ({'INFO+' if settings.is_production else 'DEBUG+'})")
    except (OSError, PermissionError) as e:
        root_logger.warning(f"无法创建 scheduler.log 文件: {e}")

    # 6. telegram.log（生产默认 INFO+，减少轮询噪音；开发仍 DEBUG+）
    try:
        _telegram_file_level = logging.INFO if settings.is_production else logging.DEBUG
        telegram_log_handler = _create_rotating_handler(
            os.path.join(log_dir, "telegram.log"),
            detailed_formatter,
            _telegram_file_level,
        )
        if use_queue:
            telegram_log_handler.addFilter(LoggerNamePrefixFilter(("app.core.telegram",)))
            listener_handlers.append(telegram_log_handler)
        else:
            logging.getLogger("app.core.telegram").addHandler(telegram_log_handler)
        _configure_named_loggers(("app.core.telegram",), _telegram_file_level, propagate=True)
        created_files.append(
            f"telegram.log ({'INFO+' if settings.is_production else 'DEBUG+'})"
        )
    except (OSError, PermissionError) as e:
        root_logger.warning(f"无法创建 telegram.log 文件: {e}")

    # 7. postback.log
    try:
        _postback_file_level = logging.INFO if settings.is_production else logging.DEBUG
        postback_log_handler = _create_rotating_handler(
            os.path.join(log_dir, "postback.log"),
            detailed_formatter,
            _postback_file_level,
        )
        postback_log_handler.addFilter(PostbackLoggerFilter())
        if use_queue:
            listener_handlers.append(postback_log_handler)
        else:
            for _postback_parent in _POSTBACK_LOGGER_PREFIXES:
                logging.getLogger(_postback_parent).addHandler(postback_log_handler)
        _configure_named_loggers(_POSTBACK_LOGGER_PREFIXES, _postback_file_level, propagate=True)
        created_files.append(f"postback.log ({'INFO+' if settings.is_production else 'DEBUG+'})")
    except (OSError, PermissionError) as e:
        root_logger.warning(f"无法创建 postback.log 文件: {e}")

    # 7.1 tracking.log
    if bool(getattr(settings, "LOG_TRACKING_FILE_ENABLED", True)):
        try:
            _tracking_file_level = logging.INFO if settings.is_production else logging.DEBUG
            tracking_log_handler = _create_rotating_handler(
                os.path.join(log_dir, "tracking.log"),
                detailed_formatter,
                _tracking_file_level,
            )
            if use_queue:
                tracking_log_handler.addFilter(LoggerNamePrefixFilter(_TRACKING_LOGGER_PREFIXES))
                listener_handlers.append(tracking_log_handler)
            else:
                for _tracking_parent in _TRACKING_LOGGER_PREFIXES:
                    logging.getLogger(_tracking_parent).addHandler(tracking_log_handler)
            _configure_named_loggers(_TRACKING_LOGGER_PREFIXES, _tracking_file_level, propagate=True)
            created_files.append(
                f"tracking.log ({'INFO+' if settings.is_production else 'DEBUG+'})"
            )
        except (OSError, PermissionError) as e:
            root_logger.warning(f"无法创建 tracking.log 文件: {e}")

    # 7.2 auth.log
    if bool(getattr(settings, "LOG_AUTH_FILE_ENABLED", True)):
        try:
            _auth_file_level = logging.INFO if settings.is_production else logging.DEBUG
            auth_log_handler = _create_rotating_handler(
                os.path.join(log_dir, "auth.log"),
                detailed_formatter,
                _auth_file_level,
            )
            if use_queue:
                auth_log_handler.addFilter(LoggerNamePrefixFilter(_AUTH_LOGGER_PREFIXES))
                listener_handlers.append(auth_log_handler)
            else:
                for _auth_parent in _AUTH_LOGGER_PREFIXES:
                    logging.getLogger(_auth_parent).addHandler(auth_log_handler)
            _configure_named_loggers(_AUTH_LOGGER_PREFIXES, _auth_file_level, propagate=True)
            created_files.append(
                f"auth.log ({'INFO+' if settings.is_production else 'DEBUG+'})"
            )
        except (OSError, PermissionError) as e:
            root_logger.warning(f"无法创建 auth.log 文件: {e}")

    # 8. debug.log：仅开发环境
    debug_log_handler = None
    if not settings.is_production:
        try:
            debug_log_handler = _create_rotating_handler(
                os.path.join(log_dir, "debug.log"),
                detailed_formatter,
                logging.DEBUG,
            )
            _attach_root_file_handler(debug_log_handler)
            created_files.append("debug.log (DEBUG+, 仅开发)")
        except (OSError, PermissionError) as e:
            root_logger.warning(f"无法创建 debug.log 文件: {e}")

    # 9. access.log
    access_log_handler = None
    try:
        access_log_handler = _create_rotating_handler(
            os.path.join(log_dir, "access.log"),
            detailed_formatter,
            logging.INFO,
        )
        if use_queue:
            access_log_handler.addFilter(LoggerNameExactFilter(("access",)))
            listener_handlers.append(access_log_handler)
        else:
            logging.getLogger("access").addHandler(access_log_handler)
        access_logger = logging.getLogger("access")
        access_logger.setLevel(logging.INFO)
        access_logger.propagate = False
        created_files.append("access.log (INFO+)")
    except (OSError, PermissionError) as e:
        root_logger.warning(f"无法创建 access.log 文件: {e}")

    # Telegram 运行时错误通知（与 error.log 落盘解耦；队列模式下进 listener）
    telegram_error_handler = None
    try:
        telegram_error_handler = _mark_handler(TelegramRuntimeErrorHandler())
        telegram_error_handler.setLevel(logging.ERROR)
        if use_queue:
            listener_handlers.append(telegram_error_handler)
        else:
            root_logger.addHandler(telegram_error_handler)
    except Exception as e:
        root_logger.warning(f"无法注册 Telegram 运行时错误通知 Handler: {e}")

    queue_handler = None
    if use_queue:
        try:
            _q_max = int(getattr(settings, "LOG_QUEUE_MAXSIZE", 20000) or 0)
            log_queue = start_log_queue_listener(listener_handlers, maxsize=_q_max)
            queue_handler = _mark_handler(make_queue_handler(log_queue))
            queue_handler.setLevel(logging.DEBUG)
            root_logger.addHandler(queue_handler)
            # access / stdout / stderr 不向上传播，需各自挂同一 QueueHandler
            for _name in ("access", "stdout", "stderr"):
                logging.getLogger(_name).addHandler(queue_handler)
        except Exception as e:
            # 启动失败则回退直写，避免完全丢日志
            stop_log_queue_listener()
            use_queue = False
            root_logger.warning(f"日志异步队列启动失败，回退直写: {e}")
            for h in listener_handlers:
                # access / 模块类带 NameFilter 的仍挂到对应 logger
                name_filters = [
                    f for f in h.filters
                    if isinstance(f, (LoggerNamePrefixFilter, LoggerNameExactFilter, PostbackLoggerFilter))
                ]
                if any(isinstance(f, LoggerNameExactFilter) for f in name_filters):
                    logging.getLogger("access").addHandler(h)
                elif any(isinstance(f, LoggerNamePrefixFilter) for f in name_filters):
                    for f in name_filters:
                        if isinstance(f, LoggerNamePrefixFilter):
                            for prefix in f.prefixes:
                                logging.getLogger(prefix).addHandler(h)
                elif any(isinstance(f, PostbackLoggerFilter) for f in name_filters):
                    for prefix in _POSTBACK_LOGGER_PREFIXES:
                        logging.getLogger(prefix).addHandler(h)
                elif h is telegram_error_handler:
                    root_logger.addHandler(h)
                else:
                    root_logger.addHandler(h)

    if created_files:
        mode_tip = "异步队列" if (use_queue and is_log_queue_running()) else "直写"
        # 降为 INFO，避免每次 fork/重建刷假告警级日志
        root_logger.info(f"日志文件已配置({mode_tip}): {', '.join(created_files)}")

    class LoggingStream:
        """将 stdout/stderr 重定向到日志文件（线程局部重入保护，避免回环）。"""

        def __init__(self, logger, log_level=logging.INFO):
            self.logger = logger
            self.log_level = log_level
            self._tls = threading.local()

        def write(self, message):
            if getattr(self._tls, "busy", False):
                return
            if message and message.strip():
                message = message.rstrip("\n\r")
                if message and not message.startswith("[STDOUT]") and not message.startswith("[STDERR]"):
                    prefix = "[STDOUT]" if self.log_level <= logging.INFO else "[STDERR]"
                    self._tls.busy = True
                    try:
                        self.logger.log(self.log_level, f"{prefix} {message}")
                    finally:
                        self._tls.busy = False

        def flush(self):
            pass

        def isatty(self):
            return False

    stdout_logger = logging.getLogger("stdout")
    stdout_logger.setLevel(logging.INFO)
    stdout_logger.propagate = False
    if not use_queue:
        if debug_log_handler:
            stdout_logger.addHandler(debug_log_handler)
        elif info_log_handler:
            stdout_logger.addHandler(info_log_handler)
        elif app_log_handler:
            stdout_logger.addHandler(app_log_handler)
        else:
            stdout_logger.addHandler(_create_console_handler(formatter, logging.INFO))

    stderr_logger = logging.getLogger("stderr")
    stderr_logger.setLevel(logging.WARNING)
    stderr_logger.propagate = False
    if not use_queue:
        if warning_log_handler:
            stderr_logger.addHandler(warning_log_handler)
        if app_log_handler:
            stderr_logger.addHandler(app_log_handler)
        if error_log_handler:
            stderr_logger.addHandler(error_log_handler)
        if not stderr_logger.handlers:
            stderr_logger.addHandler(_create_console_handler(formatter, logging.WARNING))

    sys.stdout = LoggingStream(stdout_logger, logging.INFO)
    sys.stderr = LoggingStream(stderr_logger, logging.WARNING)

    has_console = any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
        and type(h).__name__ != "QueueHandler"
        for h in root_logger.handlers
    )
    if not settings.is_production and not has_console:
        # 控制台保持同步写真实 stderr，便于开发即时查看
        root_logger.addHandler(_create_console_handler(formatter, logging.INFO))

    # APScheduler
    if scheduler_log_handler:
        for _aps_name in (
            "apscheduler",
            "apscheduler.executors.default",
            "apscheduler.schedulers",
        ):
            _aps = logging.getLogger(_aps_name)
            _aps.setLevel(logging.WARNING)
            if not use_queue:
                _aps.addHandler(scheduler_log_handler)
            _aps.propagate = True

    for _uv_name in ("uvicorn", "uvicorn.error", "gunicorn.error"):
        _uv = logging.getLogger(_uv_name)
        if not any(isinstance(f, StreamErrorFilter) for f in _uv.filters):
            _uv.addFilter(StreamErrorFilter())
