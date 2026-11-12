"""
数据库初始化模块
提供数据库创建和初始化功能
"""
import logging

from sqlalchemy import make_url

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_database_bootstrap_target(database_uri: str):
    """解析数据库引导连接，避免通过字符串替换破坏凭据或数据库名。"""
    url = make_url(str(database_uri))
    if url.get_backend_name() != "mysql":
        # SQLite 等无需单独 CREATE DATABASE，交由 SQLAlchemy 创建文件/连接。
        return None

    database_name = url.database
    if not database_name:
        raise ValueError("MySQL 数据库 URI 必须指定目标数据库名")

    # URL.set(database=None) 表示“保留原值”，并不会清除数据库名。
    # 重新创建 URL，显式不传 database，避免连接阶段自动选择目标库。
    server_url = type(url).create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        query=url.query,
    )
    return server_url, database_name


async def create_database():
    """
    创建配置指定的 MySQL 数据库（如果不存在）。

    使用不指定默认数据库的临时连接，数据库标识符由方言安全引用。
    非 MySQL 后端不需要执行 CREATE DATABASE。
    """
    target = _get_database_bootstrap_target(settings.SQLALCHEMY_DATABASE_URI)
    if target is None:
        logger.info("当前数据库后端无需单独创建数据库")
        return

    server_url, database_name = target
    temp_engine = None
    try:
        from sqlalchemy.ext.asyncio import create_async_engine

        temp_engine = create_async_engine(server_url, echo=False)
        async with temp_engine.connect() as conn:
            # 数据库名是 SQL 标识符，不能作为普通绑定参数传递。
            quoted_database = conn.dialect.identifier_preparer.quote(database_name)
            await conn.exec_driver_sql(
                f"CREATE DATABASE IF NOT EXISTS {quoted_database}"
            )
            await conn.commit()
        logger.info("目标数据库已创建或已存在")
    except Exception as exc:
        # 不记录原始异常文本，避免驱动异常意外包含连接 URI/凭据。
        logger.error("创建数据库失败：exception_type=%s", type(exc).__name__)
        raise
    finally:
        if temp_engine is not None:
            await temp_engine.dispose()
