from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
from collections.abc import AsyncGenerator  # Python 3.10+ 推荐使用 collections.abc
from fastapi import HTTPException
import logging

# ====== 修复 SQLAlchemy 2.0 与 aiomysql 0.2.0 的兼容性问题 ======
# SQLAlchemy 2.0 可能会传递 read_timeout 和 write_timeout 参数，但 aiomysql 不支持
# 使用猴子补丁来修复 SQLAlchemy 的 aiomysql 方言
logger = logging.getLogger(__name__)
try:
    from sqlalchemy.dialects.mysql import aiomysql as sqlalchemy_aiomysql
    import aiomysql as aiomysql_lib

    # 保存原始的 aiomysql.connect 函数
    _original_aiomysql_connect = aiomysql_lib.connect


    # 创建修复后的 connect 函数
    async def _patched_aiomysql_connect(*args, **kwargs):
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
# 多进程环境优化：每个 worker 进程有独立的连接池
# 使用配置中的连接池参数，优化数据库连接性能
engine = create_async_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    echo=False,  # 生产环境关闭SQL日志
    pool_pre_ping=True,  # 连接前检查连接是否有效（防止连接过期）
    pool_recycle=settings.DB_POOL_RECYCLE,  # 连接回收时间（秒）
    pool_size=settings.DB_POOL_SIZE,  # 连接池大小（每个 worker）
    max_overflow=settings.DB_MAX_OVERFLOW,  # 最大溢出连接数（每个 worker）
    connect_args={
        "connect_timeout": 10,  # 连接超时：10秒（aiomysql 支持）
    }
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
            # HTTPException是FastAPI的业务逻辑异常，不应该回滚或记录为数据库错误
            # 直接抛出，让FastAPI的异常处理器处理
            raise
        except Exception as e:
            # 发生真正的数据库异常时，回滚事务并记录错误
            logger.error(f"数据库会话错误: {str(e)}", exc_info=True)
            await session.rollback()
            raise
        finally:
            # 确保会话被关闭（释放连接）
            await session.close()


# 创建数据库表
async def create_tables():
    from app.models.models import Base
    async with engine.begin() as conn:
        # 生产环境建议使用迁移工具如Alembic
        # 这里为了演示简单，直接创建表
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")


# 初始化数据库
async def init_db():
    async with AsyncSessionLocal() as session:
        # 检查是否需要创建超级用户
        from app.models.models import User, UserRole
        from sqlalchemy.future import select

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
            # 设置密码
            admin.set_password(settings.FIRST_SUPERUSER_PASSWORD)
            session.add(admin)
            await session.commit()
            logger.info(f"Default superuser {settings.FIRST_SUPERUSER} created")
        else:
            logger.info("Superuser already exists")

    logger.info("Database initialization completed")
