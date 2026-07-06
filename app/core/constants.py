"""
应用常量定义
集中管理所有魔法数字和字符串，提高代码可维护性
"""

# ====== 密码相关常量 ======
# bcrypt算法限制：密码最大72字节
BCRYPT_MAX_PASSWORD_LENGTH = 72
# 密码最小长度
PASSWORD_MIN_LENGTH = 6

# ====== 错误信息长度限制 ======
# 错误信息最大长度（字符）
MAX_ERROR_MESSAGE_LENGTH = 1000
# 堆栈跟踪最大长度（字符）
MAX_STACK_TRACE_LENGTH = 2000

# ====== 数据库相关常量 ======
# 数据库连接池大小（每个worker）
DB_POOL_SIZE_DEFAULT = 12
# 数据库最大溢出连接数（每个worker）
DB_MAX_OVERFLOW_DEFAULT = 8
# 数据库连接回收时间（秒）
DB_POOL_RECYCLE_DEFAULT = 3600

# ====== Redis相关常量 ======
# Redis最大连接数
REDIS_MAX_CONNECTIONS_DEFAULT = 20

# ====== 分页相关常量 ======
# 默认每页大小
DEFAULT_PAGE_SIZE = 20
# 最大每页大小
MAX_PAGE_SIZE = 100
# 客户开放 API 默认/最大每页（独立于 Web 后台分页上限）
CLIENT_API_DEFAULT_PAGE_SIZE = 1000
CLIENT_API_MAX_PAGE_SIZE = 5000
# 客户开放 API 请求时间戳容差（秒）
CLIENT_API_TIME_TOLERANCE_SECONDS = 15

# ====== 计算相关常量 ======
# 百分比乘数：用于将小数转换为百分比（乘以100）
PERCENTAGE_MULTIPLIER = 100
# ECPM乘数：用于将每展示成本转换为每千次展示成本（乘以1000）
ECPM_MULTIPLIER = 1000

# ====== 文件上传相关常量 ======
# 最大文件大小（字节）：10MB
MAX_UPLOAD_SIZE_DEFAULT = 10485760
# 允许的文件扩展名
ALLOWED_UPLOAD_EXTENSIONS = ["xlsx", "xls", "csv"]

# ====== API限流相关常量 ======
# 默认API限流：每分钟请求数
API_RATE_LIMIT_DEFAULT = 100
# 登录接口限流：每分钟请求数
LOGIN_RATE_LIMIT_DEFAULT = 5

# ====== 日志相关常量 ======
# 日志文件最大大小（字节）：5MB
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024
# 日志文件备份数量
LOG_FILE_BACKUP_COUNT = 5
# 日志目录权限
LOG_DIR_MODE = 0o755

# ====== 审计日志相关常量 ======
# 审计日志保留天数（默认90天）
AUDIT_LOG_RETENTION_DAYS_DEFAULT = 90

# ====== 定时任务相关常量 ======
# 最大并发定时任务数（同一进程同时执行的任务数量）
MAX_CONCURRENT_SCHEDULED_TASKS_DEFAULT = 2
# 任务名称最大长度（字符）
MAX_TASK_NAME_LENGTH = 100
# 数据库查询超时时间（秒）
QUERY_TIMEOUT = 30

# ====== Telegram Bot相关常量 ======
# Telegram Bot启动延迟（秒）
TELEGRAM_BOT_START_DELAY = 2
# Telegram关闭消息超时（秒）
TELEGRAM_SHUTDOWN_MESSAGE_TIMEOUT = 3.0

# ====== CSRF相关常量 ======
# CSRF令牌过期时间（秒）
CSRF_TOKEN_EXPIRE_SECONDS_DEFAULT = 3600

# ====== JWT相关常量 ======
# 访问令牌默认过期时间（分钟）
ACCESS_TOKEN_EXPIRE_MINUTES_DEFAULT = 240
# 刷新令牌默认过期时间（天）
REFRESH_TOKEN_EXPIRE_DAYS_DEFAULT = 7
