"""
应用配置模块
管理应用的所有配置项，包括安全密钥、数据库连接、API配置等
使用环境变量或默认值，确保生产环境的安全性
"""
# Python 3.10+ 使用内置类型注解，只有特殊类型需要从 typing 导入
from typing import ClassVar, Dict
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, Field
from dotenv import load_dotenv
import secrets
import os
import logging

# 获取日志记录器
logger = logging.getLogger(__name__)

# 加载环境变量
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


class Settings(BaseSettings):
    """
    应用配置类
    使用Pydantic BaseSettings自动加载环境变量
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 忽略未定义的字段（如 MYSQL_DATABASE, MYSQL_USER 等，这些用于构建 DATABASE_URL）
    )

    # ====== 环境配置 ======
    # 生产环境标志（生产环境必须设置为 "production" 或 "prod"）
    # 注意：如果未设置或设置为其他值，默认为开发环境
    PRODUCTION_ENV: str = Field(
        default="development",
        description="环境类型：production/prod 为生产环境，其他为开发环境"
    )
    
    @field_validator("PRODUCTION_ENV", mode="before")
    @classmethod
    def validate_production_env(cls, v):
        """规范化环境配置值"""
        if v is None:
            return "development"
        if isinstance(v, str):
            return v.lower()
        return str(v).lower()

    @property
    def is_production(self) -> bool:
        """判断是否为生产环境
        
        使用验证后的PRODUCTION_ENV值，确保环境一致性
        """
        return self.PRODUCTION_ENV in ["production", "prod"]

    @property
    def is_development(self) -> bool:
        """判断是否为开发环境
        
        每次访问时重新检查环境变量，确保获取最新值
        """
        return not self.is_production

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
        production_env = os.getenv("PRODUCTION_ENV", "development").lower()
        is_prod = production_env in ["production", "prod"]

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
                    f"当前SECRET_KEY: {generated_key[:20]}...{generated_key[-10:]}"
                )
                logger.info(
                    "提示：开发环境可以使用随机密钥，生产环境建议设置固定的SECRET_KEY"
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
        production_env = os.getenv("PRODUCTION_ENV", "development").lower()
        is_prod = production_env in ["production", "prod"]

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
        production_env = os.getenv("PRODUCTION_ENV", "development").lower()
        is_prod = production_env in ["production", "prod"]
        
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
                v = "mysql+aiomysql://remote:kb7$rL3d8!tQ@127.0.0.1:3306/platform?charset=utf8mb4&collation=utf8mb4_0900_ai_ci"
        
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
                    logger.warning("检测到数据库连接可能包含默认密码，生产环境建议使用强密码")

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
    FIRST_SUPERUSER_PASSWORD: str = os.getenv("FIRST_SUPERUSER_PASSWORD", "admin123")

    @field_validator("FIRST_SUPERUSER_PASSWORD")
    @classmethod
    def validate_superuser_password(cls, v: str) -> str:
        """
        验证管理员密码强度
        生产环境必须设置足够复杂的密码
        """
        production_env = os.getenv("PRODUCTION_ENV", "development").lower()
        is_prod = production_env in ["production", "prod"]

        if is_prod:
            # 生产环境强制要求
            if not os.getenv("FIRST_SUPERUSER_PASSWORD"):
                logger.error("生产环境必须设置 FIRST_SUPERUSER_PASSWORD 环境变量")
                raise ValueError("生产环境必须设置 FIRST_SUPERUSER_PASSWORD 环境变量")
            if v == "admin123" or len(v) < 12:
                logger.error("生产环境管理员密码必须至少12个字符，且不能使用默认密码")
                raise ValueError("生产环境管理员密码必须至少12个字符，且不能使用默认密码")
        else:
            # 开发环境：允许使用简单密码，不显示警告
            # 仅在密码长度过短时提示
            if len(v) < 6:
                logger.warning("管理员密码长度不足6个字符，建议使用更复杂的密码")

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
    
    # Telegram Bot Token（从 BotFather 获取）
    # 生产环境必须通过环境变量设置
    TELEGRAM_TOKEN: str | None = os.getenv("TELEGRAM_TOKEN", None)

    @field_validator("TELEGRAM_TOKEN")
    @classmethod
    def validate_telegram_token(cls, v: str | None) -> str | None:
        """验证 Telegram Token"""
        production_env = os.getenv("PRODUCTION_ENV", "development").lower()
        is_prod = production_env in ["production", "prod"]
        
        if is_prod:
            # 生产环境：如果设置了但为空，给出警告
            if v is not None and (not isinstance(v, str) or not v.strip()):
                logger.warning("生产环境 TELEGRAM_TOKEN 为空，Telegram Bot 将无法启动")
        else:
            # 开发环境：允许为空（Telegram Bot 可选功能）
            if v is None or (isinstance(v, str) and not v.strip()):
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
    FACEBOOK_PIXEL_ID: str = os.getenv("FACEBOOK_PIXEL_ID", "1124622134062236")
    FACEBOOK_ACCESS_TOKEN: str = os.getenv("FACEBOOK_ACCESS_TOKEN", "EAAifTOaIZCfQBRUvZBp4OmlIpYfCX4kSOITYbBXpMEvR9hGVABb40DnmZAuOGfXCghiOmtbU9IOzVfNX4UixokNPAzRIoAJ5Wd0dXdxZBZCGoYzycyIQTx68xNOpkYc37320gqQB2SzocbiT60YEZARK9DVHLFYV83XTU6uZBHbSwnhpZCmQ4YSGTF1H7DdlFLn8iQZDZD")
    FACEBOOK_API_VERSION: str = os.getenv("FACEBOOK_API_VERSION", "v21.0")

    # 已废弃：斗篷配置已迁移至数据库表 cloak_configs（系统服务 -> 斗篷管理）
    # 该字段仅保留兼容，业务逻辑不再依赖此映射。
    FACEBOOK_PIXEL_CONFIG: ClassVar[Dict[str, Dict[str, str]]] = {}

# 创建配置实例
settings = Settings()

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
else:
    # 开发环境：不显示警告，仅在需要时提示
    # SECRET_KEY 验证已在 validate_secret_key 中处理，这里不需要额外提示
    if not os.getenv("SECRET_KEY"):
        # 仅在开发环境且使用自动生成的密钥时，静默处理（不输出日志）
        pass
