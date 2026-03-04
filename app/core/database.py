"""
数据库连接和会话管理模块

功能说明：
- 创建和管理SQLAlchemy异步数据库引擎
- 提供数据库会话依赖项（FastAPI Depends）
- 处理数据库初始化和表创建
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
from app.core.config import settings
from collections.abc import AsyncGenerator  # Python 3.10+ 推荐使用 collections.abc
from fastapi import HTTPException
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
# 
logger = logging.getLogger(__name__)
try:

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
    async with engine.begin() as conn:
        # 生产环境建议使用迁移工具如Alembic
        # 这里为了演示简单，直接创建表
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")


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
    
    Returns:
        None
    
    Raises:
        Exception: 数据库操作失败时抛出异常
    
    Example:
        # 在应用启动时自动调用，无需手动调用
        await init_db()
    """
    async with AsyncSessionLocal() as session:
        # 检查是否需要创建超级用户

        # 查询是否存在管理员用户
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
            await session.commit()
            logger.info(f"默认管理员账户已创建: {settings.FIRST_SUPERUSER}")
        else:
            logger.info("管理员账户已存在，跳过创建")

    logger.info("数据库初始化完成")
