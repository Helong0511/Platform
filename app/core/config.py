"""
应用配置模块
管理应用的所有配置项，包括安全密钥、数据库连接、API配置等
使用环境变量或默认值，确保生产环境的安全性
"""
# Python 3.10+ 使用内置类型注解，只有特殊类型需要从 typing 导入
import json
from typing import ClassVar, Dict, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, Field
from dotenv import load_dotenv
import secrets
import os
import logging
import platform

# 获取日志记录器
logger = logging.getLogger(__name__)

# 加载环境变量
# 单测/CI 由 conftest 注入环境变量，不读取 .env，避免本地生产配置干扰
if os.getenv("UNIT_TEST") != "1":
    # 使用 override=True 确保 .env 文件中的值覆盖系统环境变量
    # 如果无法读取 .env 文件（如权限问题），静默失败
    # 因为 systemd 可能已经通过 EnvironmentFile 加载了环境变量
    try:
        load_dotenv(override=True)
    except (PermissionError, IOError, OSError) as e:
        # 如果无法读取 .env 文件，记录警告但继续运行
        # 这通常发生在 systemd 服务中，因为环境变量可能已经通过 EnvironmentFile 加载
        if os.getenv("PRODUCTION_ENV"):
            # 生产环境：如果环境变量已设置，说明 systemd 已加载，可以继续
            logger.warning(f"无法读取 .env 文件（可能已通过 systemd EnvironmentFile 加载）: {e}")
        else:
            # 开发环境：给出更明确的提示
            logger.warning(f"无法读取 .env 文件: {e}")
            logger.info("如果使用 systemd 服务，请确保 .env 文件权限正确：sudo chown www-data:www-data /data/Platform/.env && sudo chmod 640 /data/Platform/.env")


def detect_production_env(explicit: str | None = None) -> str:
    """
    推断运行环境。

    - 单测（UNIT_TEST=1）：尊重环境变量 PRODUCTION_ENV
    - Windows：development（本地开发）
    - Linux（含 Ubuntu）：production
    - 其它系统：development
    """
    if os.getenv("UNIT_TEST") == "1":
        raw = explicit if explicit is not None else os.getenv("PRODUCTION_ENV", "development")
        return str(raw).lower() if raw else "development"

    system = platform.system()
    if system == "Windows":
        return "development"
    if system == "Linux":
        return "production"
    return "development"


def is_production_env_name(env_name: str) -> bool:
    return env_name in ("production", "prod")


# Windows 本机开发默认 Bot Token（仅 development 使用，生产须通过环境变量配置）
WINDOWS_DEFAULT_TELEGRAM_TOKEN = "8790845059:AAE3FrEh9S1FQcgNv6YFo1r2NrwtMS7AFOo"


class Settings(BaseSettings):
    """
    应用配置类
    使用Pydantic BaseSettings自动加载环境变量
    """
    model_config = SettingsConfigDict(
        env_file=None if os.getenv("UNIT_TEST") == "1" else ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 忽略未定义的字段（如 MYSQL_DATABASE, MYSQL_USER 等，这些用于构建 DATABASE_URL）
    )

    # ====== 环境配置 ======
    # 按运行平台自动推断：Windows → development，Linux（Ubuntu）→ production
    # 单测可通过 UNIT_TEST=1 + PRODUCTION_ENV 覆盖
    PRODUCTION_ENV: str = Field(
        default_factory=lambda: detect_production_env(),
        description="环境类型：由操作系统推断，或由单测环境变量覆盖",
    )
    
    @field_validator("PRODUCTION_ENV", mode="before")
    @classmethod
    def validate_production_env(cls, v):
        """规范化环境配置值（平台优先于 .env 中的 PRODUCTION_ENV）。"""
        resolved = detect_production_env(v)
        env_from_file = os.getenv("PRODUCTION_ENV")
        if (
            os.getenv("UNIT_TEST") != "1"
            and env_from_file
            and env_from_file.lower() != resolved
        ):
            logger.info(
                "已按运行平台(%s)使用 PRODUCTION_ENV=%s（忽略 .env 中的 %s）",
                platform.system(),
                resolved,
                env_from_file,
            )
        return resolved

    @property
    def is_production(self) -> bool:
        """判断是否为生产环境"""
        return is_production_env_name(self.PRODUCTION_ENV)

    @property
    def is_development(self) -> bool:
        """判断是否为开发环境
        
        每次访问时重新检查环境变量，确保获取最新值
        """
        return not self.is_production

    def should_run_scheduler(self) -> bool:
        """
        是否在当前进程启动 APScheduler 定时任务。

        优先级：
        1. GUNICORN_ROLE=scheduler → 独立调度进程始终启用（不受 .env 中 ENABLE_SCHEDULER=false 影响）
        2. GUNICORN_ROLE=api → 遵循 ENABLE_SCHEDULER（API 多 worker 默认关闭）
        3. SCHEDULER_WORKER=1/0（Gunicorn post_fork 为首个 API worker 设置）
        """
        role = os.getenv("GUNICORN_ROLE", "api").strip().lower()
        if role == "scheduler":
            return True

        explicit = os.getenv("ENABLE_SCHEDULER", "").strip().lower()
        if explicit in ("false", "0", "no"):
            return False
        if explicit in ("true", "1", "yes"):
            return True

        scheduler_worker = os.getenv("SCHEDULER_WORKER", "").strip()
        if scheduler_worker == "1":
            return True
        if scheduler_worker == "0":
            return False

        try:
            workers = int(os.getenv("WORKERS", "0") or "0")
        except ValueError:
            workers = 0
        if workers > 1:
            return False
        return True

    # ====== 服务器配置 ======
    API_V1_STR: str = "/api/v1"
    SERVER_NAME: str = "广告数据管理系统"
    SERVER_DESCRIPTION: str = "高性能广告数据管理平台"

    # ====== 安全配置 ======
    # SECRET_KEY用于JWT签名和加密
    # 如果环境变量中设置了SECRET_KEY，则使用环境变量的值
    # 如果未设置，则自动生成随机密钥（开发环境使用）
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """
        验证SECRET_KEY
        如果未设置，自动生成一个随机密钥（64字符，URL安全）
        """
        is_prod = is_production_env_name(detect_production_env())

        if not v or v == "your-fixed-secret-key-here":
            if is_prod:
                # 生产环境必须设置SECRET_KEY
                logger.error("生产环境必须设置 SECRET_KEY 环境变量")
                raise ValueError("生产环境必须设置 SECRET_KEY 环境变量")
            else:
                # 开发环境自动生成随机密钥（64字符，更安全）
                generated_key = secrets.token_urlsafe(64)
                logger.info(
                    f"SECRET_KEY未设置，已自动生成随机密钥（64字符）"
                )
                logger.info(
                    "提示：开发环境已自动生成 SECRET_KEY，生产环境请设置固定的 SECRET_KEY 环境变量"
                )
                return generated_key

        # 验证密钥长度（至少32个字符）
        if len(v) < 32:
            if is_prod:
                logger.error("生产环境SECRET_KEY长度必须至少32个字符")
                raise ValueError("生产环境SECRET_KEY长度必须至少32个字符")
            else:
                logger.warning("SECRET_KEY长度不足，建议至少32个字符")
        else:
            if is_prod:
                logger.info(f"✅ 使用环境变量中的SECRET_KEY（长度: {len(v)}字符）")
            else:
                logger.info(f"使用环境变量中的SECRET_KEY（长度: {len(v)}字符）")

        return v

    # ====== JWT配置 ======
    # 访问令牌过期时间（分钟）
    # 可以通过环境变量 ACCESS_TOKEN_EXPIRE_MINUTES 设置
    # 默认值：20分钟（开发环境），生产环境建议设置为 60-120 分钟
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "240"))
    # 刷新令牌过期时间（天），环境变量 REFRESH_TOKEN_EXPIRE_DAYS
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # 是否信任 X-Forwarded-For / X-Real-IP（生产环境在反向代理后应为 True）
    TRUST_PROXY_HEADERS: bool = os.getenv(
        "TRUST_PROXY_HEADERS",
        "true" if is_production_env_name(detect_production_env()) else "false",
    ).lower() in ("true", "1", "yes")

    # JWT算法配置
    # RS256（推荐，非对称加密）或 HS256（对称加密）
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "RS256")
    
    # RSA密钥配置（仅RS256算法使用）
    # RSA私钥文件路径
    RSA_PRIVATE_KEY_PATH: str = os.getenv("RSA_PRIVATE_KEY_PATH", "")
    # RSA公钥文件路径
    RSA_PUBLIC_KEY_PATH: str = os.getenv("RSA_PUBLIC_KEY_PATH", "")
    # RSA私钥内容（优先使用环境变量）
    RSA_PRIVATE_KEY: str = os.getenv("RSA_PRIVATE_KEY", "")
    # RSA公钥内容（优先使用环境变量）
    RSA_PUBLIC_KEY: str = os.getenv("RSA_PUBLIC_KEY", "")

    # ====== CORS配置 ======
    # 允许的跨域来源（生产环境必须通过环境变量设置）
    # 从环境变量读取，多个域名用逗号分隔
    # 生产环境必须设置，且不能包含localhost
    # 注意：使用字符串类型避免 pydantic-settings 自动 JSON 解析
    # 使用 Field 的 exclude=True 和 alias 来隐藏字段，通过 property 提供列表版本
    BACKEND_CORS_ORIGINS_STR: str = Field(default="", alias="BACKEND_CORS_ORIGINS", exclude=True)

    @field_validator("BACKEND_CORS_ORIGINS_STR", mode="before")
    @classmethod
    def validate_cors_origins_str(cls, v):
        """验证CORS配置字符串"""
        # 如果已经是字符串，直接返回
        if isinstance(v, str):
            return v
        # 如果是列表（从 JSON 解析），转换为逗号分隔的字符串
        if isinstance(v, list):
            return ",".join(str(item) for item in v)
        # 其他情况，从环境变量读取
        return os.getenv("BACKEND_CORS_ORIGINS", "")

    @property
    def BACKEND_CORS_ORIGINS(self) -> list[str]:
        """获取CORS来源列表"""
        is_prod = is_production_env_name(detect_production_env())

        # 从字符串字段读取
        cors_str = self.BACKEND_CORS_ORIGINS_STR or os.getenv("BACKEND_CORS_ORIGINS", "")

        if cors_str and cors_str.strip():
            # 环境变量中有配置，使用环境变量（逗号分隔）
            origins = [origin.strip() for origin in cors_str.split(",") if origin.strip()]
        else:
            # 环境变量中没有配置，使用默认值（仅开发环境）
            if is_prod:
                logger.error("生产环境必须设置 BACKEND_CORS_ORIGINS 环境变量")
                raise ValueError("生产环境必须设置 BACKEND_CORS_ORIGINS 环境变量")
            origins = [
                "http://localhost:8080",
                "http://127.0.0.1:8080",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:5174",
                "http://127.0.0.1:5174"
            ]

        # 生产环境验证：不能包含localhost或127.0.0.1
        if not is_prod:
            for origin in (
                "http://localhost:3310",
                "http://127.0.0.1:3310",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ):
                if origin not in origins:
                    origins.append(origin)

        if is_prod:
            for origin in origins:
                if "localhost" in origin.lower() or "127.0.0.1" in origin.lower():
                    logger.error(f"生产环境CORS配置不能包含localhost: {origin}")
                    raise ValueError(f"生产环境CORS配置不能包含localhost: {origin}")
                if not origin.startswith("https://"):
                    logger.warning(f"生产环境CORS配置建议使用HTTPS: {origin}")

        return origins

    # ====== 数据库配置 ======
    # 数据库连接URI
    # 生产环境必须通过环境变量DATABASE_URL设置
    # 注意：默认值包含明文密码，仅用于开发环境
    # 使用 Field 的 alias 来映射环境变量名
    SQLALCHEMY_DATABASE_URI: str = Field(
        default="mysql+aiomysql://remote:kb7$rL3d8!tQ@127.0.0.1:3306/platform?charset=utf8mb4&collation=utf8mb4_0900_ai_ci",
        alias="DATABASE_URL"
    )

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    @classmethod
    def validate_database_uri(cls, v):
        """验证数据库连接URI"""
        # 获取环境标志
        is_prod = is_production_env_name(detect_production_env())
        
        # 检查是否明确设置了 DATABASE_URL 环境变量
        explicit_database_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")
        
        # 如果 v 是 None 或空，从环境变量读取
        if not v:
            v = explicit_database_url
            if not v:
                # 如果都没有设置，使用默认值（仅开发环境）
                if is_prod:
                    logger.error("生产环境必须设置 DATABASE_URL 或 SQLALCHEMY_DATABASE_URI 环境变量")
                    raise ValueError("生产环境必须设置 DATABASE_URL 或 SQLALCHEMY_DATABASE_URI 环境变量")
                logger.error(
                    "未设置 DATABASE_URL：请在 .env 中配置，例如 "
                    "mysql+aiomysql://user:pass@127.0.0.1:3306/platform?charset=utf8mb4"
                )
                raise ValueError(
                    "必须设置 DATABASE_URL 或 SQLALCHEMY_DATABASE_URI 环境变量"
                )
        
        # 生产环境验证：如果使用默认值（未明确设置环境变量），且包含默认密码，报错
        if is_prod:
            # 只有在未明确设置 DATABASE_URL 且包含默认密码时，才报错
            # 如果用户明确设置了 DATABASE_URL，即使包含这些字符，也允许（可能是用户自己的密码）
            if not explicit_database_url:
                # 使用默认值，检查是否包含默认密码
                if "kb7$rL3d8!tQ" in v or "admin123" in v:
                    logger.error("生产环境数据库密码不能使用默认值，请设置 DATABASE_URL 环境变量")
                    raise ValueError("生产环境数据库密码不能使用默认值，请设置 DATABASE_URL 环境变量")
                logger.warning("生产环境建议通过 DATABASE_URL 环境变量设置数据库连接")
            else:
                # 用户明确设置了 DATABASE_URL，允许使用（即使包含默认密码字符，可能是用户自己的配置）
                # 只给出警告，不报错
                if "kb7$rL3d8!tQ" in v or "admin123" in v:
                    if not os.getenv("UNIT_TEST"):
                        logger.warning(
                            "检测到数据库连接可能包含默认密码，生产环境建议使用强密码"
                        )

        return v

    # 数据库连接池配置
    # 多进程环境优化：每个 worker 进程有独立的连接池
    # 高并发优化：对于短链接服务，大部分请求使用缓存，数据库压力较小
    # 推荐配置：pool_size = 10-12, max_overflow = 5-8（减少连接数以节省内存）
    # 对于 3 个 workers：总连接数 = (12 + 8) × 3 = 60（在 MySQL 默认 151 连接限制内，节省内存）
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "12"))  # 连接池大小（每个 worker），高并发优化
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "8"))  # 最大溢出连接数（每个 worker）
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # 连接回收时间（秒，1小时）

    # ====== Redis配置 ======
    # Redis连接URL（用于缓存和会话存储）
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Redis连接池配置（高并发优化）
    # 短链接和CPL服务大量使用Redis，需要更多连接
    REDIS_MAX_CONNECTIONS: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))  # 增加连接数以支持高并发

    # Redis主机地址（生产环境建议配置，用于限流和CSRF令牌存储）
    REDIS_HOST: str | None = os.getenv("REDIS_HOST", None)
    # Redis端口
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    # Redis数据库编号
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    # Redis密码（如果设置了密码）
    REDIS_PASSWORD: str | None = os.getenv("REDIS_PASSWORD", None)

    # ====== CPL系统配置 ======
    # 追踪服务基础URL（用于生成下游Tracklink和Postback URL）
    TRACKING_BASE_URL: str = Field(
        default="https://client.btfrx.online",
        description="追踪服务基础URL，用于生成下游Tracklink和Postback URL"
    )

    # ====== 管理员默认账户 ======
    # 首次启动时创建的管理员账户
    # 生产环境必须通过环境变量设置，且密码应足够复杂
    FIRST_SUPERUSER: str = os.getenv("FIRST_SUPERUSER", "admin")
    FIRST_SUPERUSER_PASSWORD: str = os.getenv("FIRST_SUPERUSER_PASSWORD", "")

    @field_validator("FIRST_SUPERUSER_PASSWORD")
    @classmethod
    def validate_superuser_password(cls, v: str) -> str:
        """
        验证管理员密码强度
        生产环境必须设置足够复杂的密码
        """
        is_prod = is_production_env_name(detect_production_env())

        if not v or not str(v).strip():
            if is_prod:
                logger.error("生产环境必须设置 FIRST_SUPERUSER_PASSWORD 环境变量")
                raise ValueError("生产环境必须设置 FIRST_SUPERUSER_PASSWORD 环境变量")
            v = secrets.token_urlsafe(16)
            logger.warning(
                "未设置 FIRST_SUPERUSER_PASSWORD，开发环境已自动生成随机密码"
            )
            return v

        if is_prod:
            if v == "admin123" or len(v) < 12:
                logger.error("生产环境管理员密码必须至少12个字符，且不能使用默认密码")
                raise ValueError("生产环境管理员密码必须至少12个字符，且不能使用默认密码")
        elif v == "admin123":
            logger.warning("检测到弱默认管理员密码 admin123，请在 .env 中修改")
        elif len(v) < 8:
            logger.warning("管理员密码长度不足8个字符，建议使用更复杂的密码")

        return v

    # ====== API限流配置 ======
    # 默认API限流：每分钟请求数
    API_RATE_LIMIT: int = int(os.getenv("API_RATE_LIMIT", "100"))
    # 登录接口限流：每分钟请求数（防止暴力破解）
    LOGIN_RATE_LIMIT: int = int(os.getenv("LOGIN_RATE_LIMIT", "5"))

    # ====== 文件上传配置 ======
    # 最大文件大小（字节）：10MB
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", "10485760"))
    # 允许的文件类型
    ALLOWED_UPLOAD_EXTENSIONS: list[str] = ["xlsx", "xls", "csv"]

    # ====== CSRF配置 ======
    # 是否启用CSRF防护（默认启用）
    ENABLE_CSRF: bool = os.getenv("ENABLE_CSRF", "true").lower() in ["true", "1", "yes"]
    # CSRF 令牌过期时间（秒）：8 小时 = 28800 秒
    CSRF_TOKEN_EXPIRE_SECONDS: int = int(os.getenv("CSRF_TOKEN_EXPIRE_SECONDS", "28800"))

    # ====== 定时任务配置 ======
    # 最大并发定时任务数（同一进程同时执行的任务数量）
    # 默认值：2（允许2个任务并发执行，充分利用进程资源）
    # 工作机制：
    #   - 有空闲槽位时：任务立即并发执行，无需排队
    #   - 达到上限时：新任务进入队列等待，有空闲槽位时自动执行
    # 建议值：
    #   - 1：严格顺序执行，适合资源紧张或任务相互依赖的场景
    #   - 2-3：推荐值，充分利用进程资源，适合大多数场景
    #   - 4+：仅当任务执行时间很短且系统资源充足时使用
    MAX_CONCURRENT_SCHEDULED_TASKS: int = int(os.getenv("MAX_CONCURRENT_SCHEDULED_TASKS", "2"))

    # ====== 日志配置 ======
    # 日志级别
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    # 日志文件路径
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/app.log")
    # 日志文件最大大小（字节）：10MB
    LOG_MAX_BYTES: int = int(os.getenv("LOG_MAX_BYTES", "10485760"))
    # 日志文件备份数量
    LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    
    # ====== 审计日志配置 ======
    # 审计日志保留天数（超过此天数的日志将被清理）
    # 默认 90 天（3个月），可根据需要调整
    # 建议值：
    #   - 30-60 天：适合高频操作场景，节省存储空间
    #   - 90-180 天：推荐值，平衡存储和查询需求
    #   - 180+ 天：适合需要长期审计的场景
    AUDIT_LOG_RETENTION_DAYS: int = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "90"))
    # 是否归档旧日志（True：归档到归档表，False：直接删除）
    # 默认 False（直接删除），因为日志数据通常不需要长期保留
    # 如果需要保留历史日志，可以设置为 True 并创建归档表
    AUDIT_LOG_ARCHIVE: bool = os.getenv("AUDIT_LOG_ARCHIVE", "false").lower() in ["true", "1", "yes"]

    # ====== 时区配置 ======
    # 应用时区（用于调度器、前端显示、数据库时间戳等）
    # 默认：Asia/Shanghai（中国时区，UTC+8）
    # 可选值：Asia/Shanghai, UTC, America/New_York 等（pytz 支持的时区）
    # 注意：
    # - 业务日期字段（如AdData.date）存储为系统时区的naive datetime
    # - 时间戳字段（如created_at、updated_at）存储为应用配置时区（默认北京时间）的naive datetime
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Shanghai")

    # ====== Telegram Bot 配置 ======
    # 是否启用 Telegram Bot 功能（默认启用）
    # 设置为 false/0/no 可禁用 Telegram 功能
    TELEGRAM_ENABLE: bool = os.getenv("TELEGRAM_ENABLE", "true").lower() in ["true", "1", "yes"]

    # ====== 追踪令牌（click_id 内嵌参数，默认关闭以保持现网行为） ======
    USE_TRACKING_TOKEN: bool = os.getenv("USE_TRACKING_TOKEN", "false").lower() in [
        "true", "1", "yes"
    ]
    AD_TRACKING_MASTER_KEY_HEX: str = os.getenv("AD_TRACKING_MASTER_KEY_HEX", "")
    # None 表示不校验令牌年龄；生产可按业务设置，例如 7776000（90 天）
    TRACKING_TOKEN_MAX_AGE_SECONDS: int | None = (
        int(os.getenv("TRACKING_TOKEN_MAX_AGE_SECONDS"))
        if os.getenv("TRACKING_TOKEN_MAX_AGE_SECONDS", "").strip()
        else None
    )
    # 令牌外层最大字符数：与 click_id varchar(255) 对齐（全场景统一，默认 255）
    TRACKING_TOKEN_MAX_OUTER_CHARS: int = int(
        os.getenv("TRACKING_TOKEN_MAX_OUTER_CHARS", "255")
    )
    # 显式 true 时即使 USE_TRACKING_TOKEN=true 也写入 clicks 表（队列批量落库）
    PERSIST_CLICKS_TO_DB: bool | None = (
        True
        if os.getenv("PERSIST_CLICKS_TO_DB", "").strip().lower() in ("true", "1", "yes")
        else False
        if os.getenv("PERSIST_CLICKS_TO_DB", "").strip().lower() in ("false", "0", "no")
        else None
    )

    # ====== 上游广告数据 API 凭证（仅 .env，代码内无默认值） ======
    TQT_APP_KEY: str = os.getenv("TQT_APP_KEY", "")
    TQT_API_SECRET: str = os.getenv("TQT_API_SECRET", "")
    
    SKYMOBI_API_ID: str = os.getenv("SKYMOBI_API_ID", "")
    SKYMOBI_API_KEY: str = os.getenv("SKYMOBI_API_KEY", "")
    
    HUGUANG_API_KEY: str = os.getenv("HUGUANG_API_KEY", "")
    HUGUANG_API_DOMAIN: str = os.getenv("HUGUANG_API_DOMAIN", "")
    HUGUANG_API_USERNAME: str = os.getenv("HUGUANG_API_USERNAME", "")
    
    TBSJ_API_USERNAME: str = os.getenv("TBSJ_API_USERNAME", "")
    TBSJ_API_PASSWORD: str = os.getenv("TBSJ_API_PASSWORD", "")

    # 定时任务拉取上游 API（TBSJ / Huguang 等）HTTP 超时与重试
    UPSTREAM_HTTP_TIMEOUT: float = float(os.getenv("UPSTREAM_HTTP_TIMEOUT", "45"))
    UPSTREAM_HTTP_CONNECT_TIMEOUT: float = float(os.getenv("UPSTREAM_HTTP_CONNECT_TIMEOUT", "15"))
    UPSTREAM_HTTP_MAX_RETRIES: int = int(os.getenv("UPSTREAM_HTTP_MAX_RETRIES", "3"))
    
    ADDERMOBI_API_USERNAME: str = os.getenv("ADDERMOBI_API_USERNAME", "")
    ADDERMOBI_API_PASSWORD: str = os.getenv("ADDERMOBI_API_PASSWORD", "")
    
    ZHISUO_API_CLIENT_ID: str = os.getenv("ZHISUO_API_CLIENT_ID", "")
    ZHISUO_API_KEY: str = os.getenv("ZHISUO_API_KEY", "")
    ZHISUO_API_CLIENT_ID_2: str = os.getenv("ZHISUO_API_CLIENT_ID_2", "")
    ZHISUO_API_KEY_2: str = os.getenv("ZHISUO_API_KEY_2", "")
    ZHISUO_API_CLIENT_ID_3: str = os.getenv("ZHISUO_API_CLIENT_ID_3", "")
    ZHISUO_API_KEY_3: str = os.getenv("ZHISUO_API_KEY_3", "")
    ZHISUO_API_CLIENT_ID_4: str = os.getenv("ZHISUO_API_CLIENT_ID_4", "")
    ZHISUO_API_KEY_4: str = os.getenv("ZHISUO_API_KEY_4", "")
    # 可选 JSON 数组，格式 [{"client_id":"...","api_key":"..."}]；若设置则优先于上述单账号变量
    ZHISUO_API_ACCOUNTS: str = os.getenv("ZHISUO_API_ACCOUNTS", "")
    ZHISUO_API_BASE_URL: str = os.getenv("ZHISUO_API_BASE_URL", "https://ch.tecnee.xyz")
    # 广告单元 / 国家报告拉数全局默认（未在 ZHISUO_API_ACCOUNT_FETCH 中配置的账号使用）
    ZHISUO_API_FETCH_UNIT: bool = os.getenv("ZHISUO_API_FETCH_UNIT", "true").lower() in [
        "true",
        "1",
        "yes",
    ]
    ZHISUO_API_FETCH_COUNTRY: bool = os.getenv("ZHISUO_API_FETCH_COUNTRY", "false").lower() in [
        "true",
        "1",
        "yes",
    ]
    # 日报兜底（channeldaily）：unit+country 均无数据时用日报补全；全局默认
    ZHISUO_API_FETCH_DAILY_FALLBACK: bool = os.getenv(
        "ZHISUO_API_FETCH_DAILY_FALLBACK", "true"
    ).lower() in [
        "true",
        "1",
        "yes",
    ]
    # 按 clientId 覆盖拉数开关，JSON 对象，如 {"zhisuo24":{"fetch_unit":true,"fetch_country":true,"fetch_daily_fallback":false}}
    ZHISUO_API_ACCOUNT_FETCH: str = os.getenv("ZHISUO_API_ACCOUNT_FETCH", "")

    POMIAD_API_BASE_URL: str = os.getenv("POMIAD_API_BASE_URL", "https://data.pomiad.com/ys_data")
    POMIAD_API_USERNAME: str = os.getenv("POMIAD_API_USERNAME", "")
    POMIAD_API_PASSWORD: str = os.getenv("POMIAD_API_PASSWORD", "")
    POMIAD_IS_BY_COUNTRY: int = int(os.getenv("POMIAD_IS_BY_COUNTRY", "0"))
    POMIAD_API_DATA_LIMIT: int = int(os.getenv("POMIAD_API_DATA_LIMIT", "100"))

    @staticmethod
    def _coerce_zhisuo_fetch_bool(value: object, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in ("true", "1", "yes")

    def _get_zhisuo_account_fetch_overrides(self) -> Dict[str, Dict[str, object]]:
        raw = (self.ZHISUO_API_ACCOUNT_FETCH or "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("ZHISUO_API_ACCOUNT_FETCH JSON 解析失败: %s", e)
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {
            str(key).strip(): value
            for key, value in parsed.items()
            if str(key).strip() and isinstance(value, dict)
        }

    def _resolve_zhisuo_fetch_flags(
        self,
        client_id: str,
        item: Dict[str, object] | None = None,
    ) -> Dict[str, bool]:
        """解析单个 zhisuo 账号的广告单元 / 国家报告 / 日报兜底拉数开关。"""
        fetch_unit = self.ZHISUO_API_FETCH_UNIT
        fetch_country = self.ZHISUO_API_FETCH_COUNTRY
        fetch_daily_fallback = self.ZHISUO_API_FETCH_DAILY_FALLBACK
        if item:
            if "fetch_unit" in item:
                fetch_unit = self._coerce_zhisuo_fetch_bool(item.get("fetch_unit"), fetch_unit)
            if "fetch_country" in item:
                fetch_country = self._coerce_zhisuo_fetch_bool(
                    item.get("fetch_country"), fetch_country
                )
            if "fetch_daily_fallback" in item:
                fetch_daily_fallback = self._coerce_zhisuo_fetch_bool(
                    item.get("fetch_daily_fallback"), fetch_daily_fallback
                )
        overrides = self._get_zhisuo_account_fetch_overrides()
        client_override = (
            overrides.get(client_id)
            or overrides.get(client_id.lower())
            or overrides.get(client_id.upper())
            or {}
        )
        if "fetch_unit" in client_override:
            fetch_unit = self._coerce_zhisuo_fetch_bool(
                client_override.get("fetch_unit"), fetch_unit
            )
        if "fetch_country" in client_override:
            fetch_country = self._coerce_zhisuo_fetch_bool(
                client_override.get("fetch_country"), fetch_country
            )
        if "fetch_daily_fallback" in client_override:
            fetch_daily_fallback = self._coerce_zhisuo_fetch_bool(
                client_override.get("fetch_daily_fallback"), fetch_daily_fallback
            )
        return {
            "fetch_unit": fetch_unit,
            "fetch_country": fetch_country,
            "fetch_daily_fallback": fetch_daily_fallback,
        }

    def get_zhisuo_accounts(self) -> List[Dict[str, object]]:
        """返回 zhisuo 账号列表，每项含 client_id、api_key、fetch_unit、fetch_country、fetch_daily_fallback。"""
        raw = (self.ZHISUO_API_ACCOUNTS or "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                logger.warning("ZHISUO_API_ACCOUNTS JSON 解析失败: %s", e)
                parsed = None
            if isinstance(parsed, list):
                accounts: List[Dict[str, object]] = []
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    client_id = str(
                        item.get("client_id") or item.get("clientId") or ""
                    ).strip()
                    api_key = str(item.get("api_key") or item.get("key") or "").strip()
                    if client_id and api_key:
                        flags = self._resolve_zhisuo_fetch_flags(client_id, item)
                        accounts.append(
                            {
                                "client_id": client_id,
                                "api_key": api_key,
                                "fetch_unit": flags["fetch_unit"],
                                "fetch_country": flags["fetch_country"],
                                "fetch_daily_fallback": flags["fetch_daily_fallback"],
                            }
                        )
                if accounts:
                    return accounts

        accounts: List[Dict[str, object]] = []
        for client_id, api_key in (
            (self.ZHISUO_API_CLIENT_ID, self.ZHISUO_API_KEY),
            (self.ZHISUO_API_CLIENT_ID_2, self.ZHISUO_API_KEY_2),
            (self.ZHISUO_API_CLIENT_ID_3, self.ZHISUO_API_KEY_3),
            (self.ZHISUO_API_CLIENT_ID_4, self.ZHISUO_API_KEY_4),
        ):
            cid = (client_id or "").strip()
            key = (api_key or "").strip()
            if cid and key:
                flags = self._resolve_zhisuo_fetch_flags(cid)
                accounts.append(
                    {
                        "client_id": cid,
                        "api_key": key,
                        "fetch_unit": flags["fetch_unit"],
                        "fetch_country": flags["fetch_country"],
                        "fetch_daily_fallback": flags["fetch_daily_fallback"],
                    }
                )
        return accounts

    # ====== 敏感路径防护（防扫描 / 探测） ======
    ENABLE_SENSITIVE_PATH_GUARD: bool = os.getenv(
        "ENABLE_SENSITIVE_PATH_GUARD", "true"
    ).lower() in ["true", "1", "yes"]
    SENSITIVE_PATH_BLOCK_EXTRA: str = os.getenv("SENSITIVE_PATH_BLOCK_EXTRA", "")
    SENSITIVE_PATH_PROBE_RETENTION_DAYS: int = int(
        os.getenv("SENSITIVE_PATH_PROBE_RETENTION_DAYS", "90")
    )
    SENSITIVE_PATH_HIT_WINDOW_SECONDS: int = int(
        os.getenv("SENSITIVE_PATH_HIT_WINDOW_SECONDS", "1800")
    )
    SENSITIVE_PATH_AUTO_BLOCK_MEDIUM: int = int(
        os.getenv("SENSITIVE_PATH_AUTO_BLOCK_MEDIUM", "50")
    )
    SENSITIVE_PATH_AUTO_BLOCK_HIGH: int = int(
        os.getenv("SENSITIVE_PATH_AUTO_BLOCK_HIGH", "20")
    )
    SENSITIVE_PATH_AUTO_BLOCK_CRITICAL: int = int(
        os.getenv("SENSITIVE_PATH_AUTO_BLOCK_CRITICAL", "5")
    )
    SENSITIVE_PATH_ALERT_CRITICAL: bool = os.getenv(
        "SENSITIVE_PATH_ALERT_CRITICAL", "true"
    ).lower() in ["true", "1", "yes"]
    SENSITIVE_PATH_ALERT_DEBOUNCE_SECONDS: int = int(
        os.getenv("SENSITIVE_PATH_ALERT_DEBOUNCE_SECONDS", "300")
    )
    
    # Telegram Bot Token（从 BotFather 获取）
    # 生产环境必须通过环境变量设置；Windows 本机开发见 validate_telegram_token
    TELEGRAM_TOKEN: str | None = os.getenv("TELEGRAM_TOKEN", None)

    @field_validator("TELEGRAM_TOKEN", mode="before")
    @classmethod
    def validate_telegram_token(cls, v: str | None) -> str | None:
        """验证 Telegram Token；Windows 本机开发使用内置默认 Token。"""
        is_prod = is_production_env_name(detect_production_env())

        if not is_prod and platform.system() == "Windows":
            logger.info("Windows 本机开发环境，使用默认 TELEGRAM_TOKEN")
            return WINDOWS_DEFAULT_TELEGRAM_TOKEN

        if is_prod:
            if v is not None and (not isinstance(v, str) or not v.strip()):
                logger.warning("生产环境 TELEGRAM_TOKEN 为空，Telegram Bot 将无法启动")
        elif v is None or (isinstance(v, str) and not v.strip()):
            logger.info("开发环境未设置 TELEGRAM_TOKEN，Telegram Bot 功能将不可用")

        return v

    # Telegram 管理员 Chat ID（用于接收系统通知）
    # 可以是用户 ID（如 "123456789"）或群组 ID（如 "-1001234567890"）
    # 获取方式：向 Bot 发送 /id 命令，或使用 @userinfobot
    TELEGRAM_ADMIN: str | None = os.getenv("TELEGRAM_ADMIN", None)

    @field_validator("TELEGRAM_ADMIN")
    @classmethod
    def validate_telegram_admin(cls, v: str | None) -> str | None:
        """验证 Telegram Admin Chat ID
        支持单个 ID 或多个 ID（逗号分隔）
        """
        if v is not None and isinstance(v, str):
            v = v.strip()
            if v:
                # 支持逗号分隔的多个 ID
                ids = [id.strip() for id in v.split(",")]
                for id in ids:
                    # 验证格式：应该是数字字符串（可能带负号）
                    if not id.replace("-", "").isdigit():
                        logger.warning(f"TELEGRAM_ADMIN 格式可能不正确: {id}（应为数字字符串）")
        return v

    # ====== Facebook 像素配置 ======
    # 全局默认 Facebook 像素配置（作为兜底配置）
    FACEBOOK_PIXEL_ID: str = os.getenv("FACEBOOK_PIXEL_ID", "")
    FACEBOOK_ACCESS_TOKEN: str = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
    FACEBOOK_API_VERSION: str = os.getenv("FACEBOOK_API_VERSION", "v23.0")

    # 已废弃：斗篷配置已迁移至数据库表 cloak_configs（系统服务 -> 斗篷管理）
    # 该字段仅保留兼容，业务逻辑不再依赖此映射。
    FACEBOOK_PIXEL_CONFIG: ClassVar[Dict[str, Dict[str, str]]] = {}

# 创建配置实例
settings = Settings()

# 将 settings 中的追踪密钥同步到 os.environ，供 AdTrackingCodec 与旧代码路径一致读取
if settings.AD_TRACKING_MASTER_KEY_HEX.strip():
    os.environ.setdefault(
        "AD_TRACKING_MASTER_KEY_HEX",
        settings.AD_TRACKING_MASTER_KEY_HEX.strip(),
    )

# 验证关键配置
if settings.is_production:
    # 生产环境配置验证
    # 验证SECRET_KEY
    if not os.getenv("SECRET_KEY"):
        logger.error("生产环境必须设置 SECRET_KEY 环境变量")

    # 验证数据库连接
    if not os.getenv("DATABASE_URL"):
        logger.error("生产环境必须设置 DATABASE_URL 环境变量")

    # 验证管理员密码
    if not os.getenv("FIRST_SUPERUSER_PASSWORD") or settings.FIRST_SUPERUSER_PASSWORD == "admin123":
        logger.error("生产环境必须设置复杂的第一管理员密码（FIRST_SUPERUSER_PASSWORD）")

    # 验证CORS配置
    cors_origins_str = str(settings.BACKEND_CORS_ORIGINS)
    if "localhost" in cors_origins_str or "127.0.0.1" in cors_origins_str:
        logger.warning("CORS配置包含localhost，生产环境建议移除")

    if settings.USE_TRACKING_TOKEN:
        from app.core.tracking.ad_tracking_codec import AdTrackingCodec

        key_hex = settings.AD_TRACKING_MASTER_KEY_HEX.strip()
        if not key_hex:
            logger.error(
                "生产环境 USE_TRACKING_TOKEN=true 必须设置 AD_TRACKING_MASTER_KEY_HEX"
            )
        elif key_hex == AdTrackingCodec._DEFAULT_KEY_HEX:
            logger.error(
                "生产环境不得使用 AdTrackingCodec 内置开发默认密钥，请配置独立密钥"
            )
    if not settings.HUGUANG_API_KEY.strip():
        logger.warning("生产环境未配置 HUGUANG_API_KEY，Huguang 定时任务将跳过")
    if not settings.TQT_APP_KEY.strip():
        logger.warning("生产环境未配置 TQT_APP_KEY，TQT 定时任务将跳过")
else:
    # 开发环境：不显示警告，仅在需要时提示
    # SECRET_KEY 验证已在 validate_secret_key 中处理，这里不需要额外提示
    if not os.getenv("SECRET_KEY"):
        # 仅在开发环境且使用自动生成的密钥时，静默处理（不输出日志）
        pass
