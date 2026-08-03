"""
Gunicorn 配置文件
生产环境使用 Gunicorn + Uvicorn Workers 运行 FastAPI 应用
服务器配置：2核CPU + 4GB内存
后端端口：8960
"""
import multiprocessing
import os
import logging

# 获取日志记录器（用于配置加载时的日志输出）
logger = logging.getLogger(__name__)

# 导入配置（用于判断是否为生产环境）
from app.core.config import settings

# api = Platform-backend（HTTP）；scheduler = Platform-scheduler（仅定时任务，独立 pid/日志）
GUNICORN_ROLE = os.getenv("GUNICORN_ROLE", "api").strip().lower()

# ====== 服务器配置 ======
# 绑定地址和端口
bind = (
    os.getenv("SCHEDULER_BIND", "127.0.0.1:8961")
    if GUNICORN_ROLE == "scheduler"
    else "127.0.0.1:8960"
)  # API:8960；调度:8961（仅本机，勿经 Nginx 暴露）

# Worker 配置
# 根据 CPU 核心数自动计算 worker 数量
# 推荐公式: workers = (2 × CPU核心数) + 1
# 对于小内存服务器（< 8GB），可以适当减少 worker 数量
cpu_count = multiprocessing.cpu_count()

# 根据服务器配置智能设置 worker 数量
# 可以通过环境变量 WORKERS 覆盖
if os.getenv("WORKERS"):
    workers = int(os.getenv("WORKERS"))
else:
    # 默认使用推荐公式
    workers = (cpu_count * 2) + 1
    
    # 小内存服务器优化（如果内存 < 8GB，适当减少 workers）
    # 可以通过环境变量 MEMORY_GB 指定内存大小
    memory_gb = int(os.getenv("MEMORY_GB", "0"))
    if memory_gb > 0 and memory_gb < 8:
        # 小内存服务器：每个 worker 约占用 200-300MB，限制最大 workers
        max_workers = max(2, memory_gb // 2)  # 确保至少2个worker
        workers = min(workers, max_workers)

# 2核CPU + 4GB内存，固定为 3 个 worker（仅 API 服务；勿覆盖 WORKERS 环境变量）
if cpu_count == 2 and GUNICORN_ROLE != "scheduler" and not os.getenv("WORKERS"):
    workers = 3

if GUNICORN_ROLE == "scheduler":
    workers = 1

worker_class = "app.core.uvicorn_worker.NoProxyHeadersUvicornWorker"
worker_connections = 1000  # 每个 worker 的最大连接数（Uvicorn默认1000，适合高并发）
max_requests = 5000  # 每个 worker 处理的最大请求数（提高以支持高并发，定期重启防止内存泄漏）
max_requests_jitter = 250  # 随机抖动，避免所有 worker 同时重启

# ====== 超时配置 ======
# 与 Nginx location /api/ 的 proxy_read_timeout=120s 对齐，避免 Worker 先杀导致 502
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
keepalive = 10  # Keep-alive 连接时间（秒），增加以支持高并发短连接复用
graceful_timeout = 30  # 优雅关闭超时时间（秒），确保任务完成
timeout_graceful_shutdown = 30  # 优雅关闭超时（秒），等待 worker 完成当前请求

# ====== 日志配置 ======
# 确保日志目录存在并设置权限
log_dir = os.path.join(os.path.dirname(__file__), "logs")
try:
    os.makedirs(log_dir, exist_ok=True, mode=0o755)
    # 尝试设置目录权限（如果可能）
    try:
        import stat
        os.chmod(log_dir, 0o755)
    except (OSError, PermissionError):
        pass  # 如果没有权限设置，继续执行
except (OSError, PermissionError) as e:
    logger.warning(f"无法创建日志目录 {log_dir}: {e}")

# 日志文件路径（调度进程与 API 进程分离，避免争用同一文件）
# GUNICORN_ACCESSLOG_ENABLED=false 时可关闭 access（应用侧已有 access.log 且生产已降噪）
_accesslog_enabled = os.getenv("GUNICORN_ACCESSLOG_ENABLED", "false").lower() in ("true", "1", "yes")
if GUNICORN_ROLE == "scheduler":
    accesslog = os.path.join(log_dir, "gunicorn_scheduler_access.log") if _accesslog_enabled else None
    errorlog = os.path.join(log_dir, "gunicorn_scheduler_error.log")
else:
    accesslog = os.path.join(log_dir, "gunicorn_access.log") if _accesslog_enabled else None
    errorlog = os.path.join(log_dir, "gunicorn_error.log")

# 尝试创建日志文件并设置权限（如果可能）
for log_file in [accesslog, errorlog]:
    if not log_file:
        continue
    try:
        # 如果文件不存在，创建空文件
        if not os.path.exists(log_file):
            open(log_file, 'a').close()
        # 尝试设置文件权限
        try:
            os.chmod(log_file, 0o644)
        except (OSError, PermissionError):
            pass  # 如果没有权限设置，继续执行
    except (OSError, PermissionError) as e:
        logger.warning(f"无法创建或设置权限日志文件 {log_file}: {e}")

# 日志级别
loglevel = "warning"  # 生产环境使用 warning，减少日志量

# 日志格式
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ====== 进程配置 ======
# 进程名称
proc_name = "platform_scheduler" if GUNICORN_ROLE == "scheduler" else "platform_backend"

# 守护进程模式（通过 systemd 管理，不需要守护进程）
daemon = False

# PID 文件（两个 Gunicorn 实例不可共用同一 pidfile）
pidfile = os.path.join(
    log_dir,
    "gunicorn_scheduler.pid" if GUNICORN_ROLE == "scheduler" else "gunicorn.pid",
)
# 尝试创建 PID 文件目录并设置权限（如果可能）
try:
    if not os.path.exists(pidfile):
        open(pidfile, 'a').close()
    try:
        os.chmod(pidfile, 0o644)
    except (OSError, PermissionError):
        pass
except (OSError, PermissionError) as e:
    logger.warning(f"无法创建或设置权限 PID 文件 {pidfile}: {e}")

# ====== 性能配置 ======
# 预加载应用（提高性能，但会增加内存使用）
# 预加载可以减少启动时间，但会增加内存占用
# 多进程环境：预加载可以共享代码，但每个 worker 仍需要独立初始化
# 可以通过环境变量 PRELOAD_APP 控制
# 
# 注意：对于 4GB 内存服务器，建议关闭 preload 以节省内存
# 如果服务器内存充足（>= 8GB），可以启用 preload 提升性能
preload_env = os.getenv("PRELOAD_APP", "false").lower()
if preload_env in ["true", "1", "yes"]:
    preload_app = True
    logger.info("已启用应用预加载（preload_app=True），将增加内存使用")
else:
    preload_app = False  # 默认关闭以节省内存（4GB服务器）
    if not settings.is_production:
        logger.debug("应用预加载已关闭（preload_app=False），如需启用请设置环境变量 PRELOAD_APP=true")

# Worker 临时文件目录
# Ubuntu 22.04.5 优化：使用内存文件系统（如果可用）可以提高性能
# /dev/shm 是 Linux 内存文件系统，通常大小为系统内存的 50%
worker_tmp_dir = "/dev/shm"  # Linux 内存文件系统
# 如果 /dev/shm 不可用，会在系统临时目录创建
# 注意：确保 /dev/shm 有足够的空间（至少 512MB）

# ====== 安全配置 ======
# 限制请求行大小
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# ====== 统计和监控 ======
# 统计信息（可选）
# statsd_host = "localhost:8125"
# statsd_prefix = "platform_backend"

# ====== 环境变量 ======
# 确保加载环境变量
raw_env = [
    f"PRODUCTION_ENV={os.getenv('PRODUCTION_ENV', 'production')}",
    f"WORKERS={workers}",
]

# ====== 访问日志配置 ======
# 默认 GUNICORN_ACCESSLOG_ENABLED=false：不写 gunicorn_*_access.log，避免与应用 access.log 双写。
# 应用侧 RequestLoggingMiddleware 已解码路径并按生产降噪策略写入 logs/access.log。
# 需要对照 Nginx/Gunicorn 原始 access 时再设 GUNICORN_ACCESSLOG_ENABLED=true。

# ====== Hook 函数 ======
# 多进程环境优化：每个 hook 都会在每个 worker 中执行
def on_starting(server):
    """服务器启动时的回调（主进程）"""
    name = "Platform Scheduler" if GUNICORN_ROLE == "scheduler" else "Platform Backend"
    server.log.info(f"{name} 正在启动...")
    server.log.info(f"Worker 数量: {workers}, Worker 类: {worker_class}, role={GUNICORN_ROLE}")

def on_reload(server):
    """重新加载时的回调（主进程）"""
    server.log.info("Platform Backend 正在重新加载...")

def when_ready(server):
    """服务器就绪时的回调（主进程）"""
    server.log.info("Platform Backend 已就绪，监听 %s", server.address)
    server.log.info(f"配置: {workers} workers, timeout={timeout}s, max_requests={max_requests}")

def post_fork(server, worker):
    """Worker 进程启动后的回调（每个 worker 进程）"""
    if GUNICORN_ROLE == "scheduler":
        # 独立调度服务仅 1 个 worker，始终跑定时任务
        os.environ["SCHEDULER_WORKER"] = "1"
    else:
        # API 服务：仅首个 worker 运行定时任务（若未设置 ENABLE_SCHEDULER=false）
        os.environ["SCHEDULER_WORKER"] = "1" if worker.age == 0 else "0"
    worker.log.info(
        f"Worker {worker.pid} 已启动（父进程: {os.getppid()}，"
        f"role={GUNICORN_ROLE}，SCHEDULER_WORKER={os.environ['SCHEDULER_WORKER']}）"
    )
    # preload 时 master 已起 QueueListener，fork 后线程失效，必须在 worker 内重建
    if preload_app and getattr(settings, "LOG_QUEUE_ENABLED", True):
        try:
            from app.bootstrap.logging_setup import configure_logging

            configure_logging()
            worker.log.info("Worker %s 已重建异步日志队列（preload 安全）", worker.pid)
        except Exception as e:
            worker.log.warning("Worker %s 重建日志队列失败: %s", worker.pid, e)

def worker_int(worker):
    """Worker 中断时的回调（每个 worker 进程）"""
    worker.log.info("Worker %s 收到中断信号", worker.pid)

def worker_abort(worker):
    """Worker 异常退出时的回调（每个 worker 进程）"""
    worker.log.error("Worker %s 异常退出", worker.pid)

def worker_exit(server, worker):
    """Worker 退出前排空异步日志队列（max_requests 轮转 / 优雅停机）。"""
    try:
        from app.core.log_queue import shutdown_log_queue

        shutdown_log_queue(timeout_sec=2.0)
    except Exception:
        pass

def on_exit(server):
    """服务器退出时的回调（主进程）"""
    server.log.info("Platform Backend 正在退出...")
    try:
        from app.core.log_queue import shutdown_log_queue

        shutdown_log_queue(timeout_sec=1.0)
    except Exception:
        pass

