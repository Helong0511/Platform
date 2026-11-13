"""
数据库连接和会话管理模块

功能说明：
- 创建和管理SQLAlchemy异步数据库引擎
- 提供数据库会话依赖项（FastAPI Depends）
- 管理数据库连接与会话；schema 仅由独立 Migration Runner 管理
- 修复SQLAlchemy 2.0与aiomysql的兼容性问题

数据库配置：
- 使用异步引擎（create_async_engine）
- 支持连接池配置（pool_size, max_overflow等）
- 自动连接回收（pool_recycle）
- 连接前检查（pool_pre_ping）

多进程环境优化：
- 每个worker进程有独立的连接池
- 总连接数 = (pool_size + max_overflow) × workers
- 建议配置：pool_size=12, max_overflow=8, workers=3
- 总连接数 = (12 + 8) × 3 = 60（在MySQL默认151限制内）

注意事项：
1. 所有数据库操作都使用异步会话（AsyncSession）
2. 会话自动提交和回滚（通过get_db依赖项）
3. HTTPException不会触发数据库回滚
4. 生产环境建议使用Alembic进行数据库迁移
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.dialects.mysql import aiomysql as sqlalchemy_aiomysql
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from collections.abc import AsyncGenerator  # Python 3.10+ 推荐使用 collections.abc
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
import logging
import aiomysql as aiomysql_lib

from app.models.models import Base, User, UserRole

# ====== 日志记录器 ======
logger = logging.getLogger(__name__)

# ====== 修复 SQLAlchemy 2.0 与 aiomysql 0.2.0 的兼容性问题 ======
# 
# 问题说明：
# SQLAlchemy 2.0 可能会传递 read_timeout 和 write_timeout 参数给 aiomysql.connect()
# 但 aiomysql 0.2.0 不支持这些参数，会导致连接失败
# 
# 解决方案：
# 使用猴子补丁（monkey patch）拦截 aiomysql.connect() 调用
# 过滤掉不支持的参数，只保留 aiomysql 支持的参数
# 
# 支持的参数列表：
# - host, port, user, password, db: 连接基本信息
# - charset: 字符集（默认utf8mb4）
# - connect_timeout: 连接超时（秒）
# - autocommit: 自动提交模式
# - loop: 事件循环（已弃用，Python 3.10+不需要）
# - minsize, maxsize: 连接池大小（用于连接池模式）
# 
# 不支持的参数（会被过滤）：
# - read_timeout: 读取超时
# - write_timeout: 写入超时
# - collation: URL 查询参数，不能作为 connect() 关键字参数
# 
try:
    # 保存原始的 aiomysql.connect 函数
    _original_aiomysql_connect = aiomysql_lib.connect

    # 创建修复后的 connect 函数
    async def _patched_aiomysql_connect(*args, **kwargs):
        """过滤 SQLAlchemy 传入 aiomysql 不支持的超时参数后建立连接。"""
        # 过滤掉 aiomysql 不支持的参数
        # aiomysql 支持的参数：host, port, user, password, db, charset, connect_timeout, autocommit, loop, minsize, maxsize
        supported_params = {
            'host', 'port', 'user', 'password', 'db', 'charset',
            'connect_timeout', 'autocommit', 'loop', 'minsize', 'maxsize'
        }
        # 移除不支持的参数（如 read_timeout, write_timeout）
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in supported_params}
        # 确保 connect_timeout 有默认值
        if 'connect_timeout' not in filtered_kwargs:
            filtered_kwargs['connect_timeout'] = 10
        # 调用原始的 connect 函数
        return await _original_aiomysql_connect(*args, **filtered_kwargs)

    # 应用猴子补丁到 aiomysql 模块
    aiomysql_lib.connect = _patched_aiomysql_connect
    logger.info("已应用 aiomysql.connect 兼容性修复（过滤 read_timeout/write_timeout 参数）")
except Exception as e:
    # 如果应用补丁失败，记录警告但继续运行
    logger.warning(f"应用 aiomysql 兼容性补丁失败: {e}")

# ====== 创建数据库引擎 ======
_db_url = str(settings.SQLALCHEMY_DATABASE_URI)
_engine_kwargs = {
    "echo": False,
    "pool_pre_ping": True,
}
if _db_url.startswith("sqlite"):
    # 单测/CI 内存 SQLite 不支持 pool_size/max_overflow
    engine = create_async_engine(_db_url, **_engine_kwargs)
else:
    engine = create_async_engine(
        _db_url,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        connect_args={
            "connect_timeout": 10,
        },
        **_engine_kwargs,
    )
# 多进程环境说明：
# - 每个 worker 进程有独立的连接池
# - 总连接数 = (pool_size + max_overflow) × workers
# - 例如：3 workers × (15 + 10) = 75 个连接（在 MySQL 默认 151 限制内）

# 创建异步会话工厂
# SQLAlchemy 2.0+ 推荐使用 async_sessionmaker 替代 sessionmaker(class_=AsyncSession)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ====== 数据库依赖项 ======
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话的FastAPI依赖项
    
    这是一个异步生成器，用于为每个请求提供数据库会话
    自动处理事务提交和回滚
    
    使用方式:
        async def some_endpoint(db: AsyncSession = Depends(get_db)):
            # 使用db进行数据库操作
            pass
    
    异常处理:
        - 如果发生异常，自动回滚事务
        - 无论成功或失败，都会关闭会话
    """
    async with AsyncSessionLocal() as session:
        try:
            # 生成会话，供请求处理函数使用
            yield session
            # 如果没有异常，提交事务
            await session.commit()
        except HTTPException:
            await session.rollback()
            raise
        except RequestValidationError:
            await session.rollback()
            raise
        except Exception as e:
            # 发生真正的数据库异常时，回滚事务并记录错误
            # SQLAlchemy 异常消息可能包含绑定参数；日志只保留异常类型，不记录原始数据。
            logger.error("数据库会话错误：exception_type=%s", type(e).__name__)
            await session.rollback()
            raise
        finally:
            # 确保会话被关闭（释放连接）
            await session.close()


async def get_postback_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Postback S2S 专用数据库会话：不在请求结束时自动 commit。

    事务由 PostbackProcessor 显式 commit/rollback，避免与 get_db 二次提交冲突。
  """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except HTTPException:
            await session.rollback()
            raise
        except RequestValidationError:
            await session.rollback()
            raise
        except Exception as e:
            # Postback 参数可能包含 IP、邮箱、click_id 等 PII，禁止写入异常日志。
            logger.error("Postback 数据库会话错误：exception_type=%s", type(e).__name__)
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_readonly() -> AsyncGenerator[AsyncSession, None]:
    """
    只读查询专用会话：成功路径 rollback 而非 commit。

    用于转化汇总等 GET 接口，防止业务层误 flush/update 被 get_db 自动提交。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.rollback()
        except HTTPException:
            await session.rollback()
            raise
        except RequestValidationError:
            await session.rollback()
            raise
        except Exception as e:
            # 只读查询错误同样不输出 SQL 参数或原始异常文本。
            logger.error("只读数据库会话错误：exception_type=%s", type(e).__name__)
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables():
    """兼容旧调用名，但禁止应用进程绕过 Migration Runner 执行 DDL。"""
    raise RuntimeError(
        "禁止在应用运行进程中调用 create_tables；"
        "请使用独立 MIGRATION_DATABASE_URL 执行 python -m app.db.migrations apply"
    )


def _is_duplicate_key_integrity_error(exc: IntegrityError) -> bool:
    """仅识别唯一键竞争；其它完整性错误必须继续抛出。"""
    original = getattr(exc, "orig", exc)
    args = getattr(original, "args", ())
    if args and args[0] == 1062:
        return True
    message = str(original).lower()
    return "duplicate entry" in message or "unique constraint failed" in message


async def init_db():
    """
    初始化数据库
    
    功能说明：
    - 检查是否存在管理员用户
    - 如果不存在，创建默认管理员账户
    - 默认管理员账户信息从settings配置读取
    
    默认管理员配置：
    - 用户名：settings.FIRST_SUPERUSER（默认"admin"）
    - 密码：settings.FIRST_SUPERUSER_PASSWORD（生产环境必须设置）
    - 角色：ADMIN（管理员）
    - 邮箱：{username}@example.com
    
    安全注意事项：
    - 生产环境必须通过环境变量设置复杂的管理员密码
    - 首次启动后建议修改默认管理员密码
    - 建议创建额外的管理员账户，然后禁用默认账户
    
    执行时机：
    - 应用启动时自动执行（在lifespan启动阶段）
    - 只在没有管理员用户时创建，避免重复创建
    """
    async with AsyncSessionLocal() as session:
        # 检查是否需要创建超级用户
        result = await session.execute(select(User).where(User.role == UserRole.ADMIN))
        admin = result.scalars().first()

        if not admin:
            # 创建默认超级用户
            admin = User(
                username=settings.FIRST_SUPERUSER,
                email=f"{settings.FIRST_SUPERUSER}@example.com",
                role=UserRole.ADMIN,
                is_active=True,
                login_restricted=False
            )
            # 设置密码（自动加密）
            admin.set_password(settings.FIRST_SUPERUSER_PASSWORD)
            session.add(admin)
            try:
                await session.commit()
                logger.info(f"默认管理员账户已创建: {settings.FIRST_SUPERUSER}")
            except IntegrityError as exc:
                await session.rollback()
                if not _is_duplicate_key_integrity_error(exc):
                    raise
                # 多个 Worker 同时启动时可能同时读到“无管理员”；
                # 唯一键只允许一个 Worker 创建成功，其它 Worker 回滚后确认结果即可。
                concurrent_result = await session.execute(
                    select(User).where(User.role == UserRole.ADMIN)
                )
                concurrent_admin = concurrent_result.scalars().first()
                if concurrent_admin is None:
                    raise
                logger.info("默认管理员账户已由其它 Worker 并发创建")
        else:
            logger.info("管理员账户已存在，跳过创建")

    logger.info("数据库初始化完成")
