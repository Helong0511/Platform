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

# ====== 服务器配置 ======
# 绑定地址和端口
bind = "127.0.0.1:8960"  # 后端端口，只监听本地，通过 Nginx 反向代理

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

# 2核CPU + 4GB内存，固定为 3 个 worker
# 高并发优化：对于短链接和CPL服务，3个worker可以处理约3000并发连接
if cpu_count == 2:
    workers = 3

worker_class = "uvicorn.workers.UvicornWorker"  # 使用 Uvicorn Worker
worker_connections = 1000  # 每个 worker 的最大连接数（Uvicorn默认1000，适合高并发）
max_requests = 1000  # 每个 worker 处理的最大请求数（提高以支持高并发，定期重启防止内存泄漏）
max_requests_jitter = 50  # 随机抖动，避免所有 worker 同时重启

# ====== 超时配置 ======
# Ubuntu 22.04.5 生产环境优化（高并发场景）
timeout = 60  # Worker 超时时间（秒），短链接重定向应该很快，减少超时时间
keepalive = 10  # Keep-alive 连接时间（秒），增加以支持高并发短连接复用
graceful_timeout = 30  # 优雅关闭超时时间（秒），确保任务完成
timeout_graceful_shutdown = 30  # 优雅关闭超时（秒），等待 worker 完成当前请求

# ====== 日志配置 ======
# 日志文件路径
accesslog = os.path.join(os.path.dirname(__file__), "logs", "gunicorn_access.log")
errorlog = os.path.join(os.path.dirname(__file__), "logs", "gunicorn_error.log")

# 日志级别
loglevel = "warning"  # 生产环境使用 warning，减少日志量

# 日志格式
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ====== 进程配置 ======
# 进程名称
proc_name = "platform_backend"

# 守护进程模式（通过 systemd 管理，不需要守护进程）
daemon = False

# PID 文件
pidfile = os.path.join(os.path.dirname(__file__), "logs", "gunicorn.pid")

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
]

# ====== 访问日志配置 ======
# 注意：uvicorn worker 的访问日志会显示 URL 编码的路径
# 我们已经在 RequestLoggingMiddleware 中解码了路径，应用日志（logs/app.log）会显示正确的中文路径
# Gunicorn 访问日志（logs/gunicorn_access.log）仍会显示 URL 编码，但应用日志已解码
# 
# 如果需要完全禁用 Gunicorn 访问日志，只使用应用日志，可以设置：
# accesslog = "-"

# ====== Hook 函数 ======
# 多进程环境优化：每个 hook 都会在每个 worker 中执行
def on_starting(server):
    """服务器启动时的回调（主进程）"""
    server.log.info("Platform Backend 正在启动...")
    server.log.info(f"Worker 数量: {workers}, Worker 类: {worker_class}")

def on_reload(server):
    """重新加载时的回调（主进程）"""
    server.log.info("Platform Backend 正在重新加载...")

def when_ready(server):
    """服务器就绪时的回调（主进程）"""
    server.log.info("Platform Backend 已就绪，监听 %s", server.address)
    server.log.info(f"配置: {workers} workers, timeout={timeout}s, max_requests={max_requests}")

def post_fork(server, worker):
    """Worker 进程启动后的回调（每个 worker 进程）"""
    import os
    worker.log.info(f"Worker {worker.pid} 已启动（父进程: {os.getppid()}）")

def worker_int(worker):
    """Worker 中断时的回调（每个 worker 进程）"""
    worker.log.info("Worker %s 收到中断信号", worker.pid)

def worker_abort(worker):
    """Worker 异常退出时的回调（每个 worker 进程）"""
    worker.log.error("Worker %s 异常退出", worker.pid)

def on_exit(server):
    """服务器退出时的回调（主进程）"""
    server.log.info("Platform Backend 正在退出...")

