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
    兼容旧调用名，但永久禁止应用数据库账号创建数据库。

    数据库实例/schema provisioning 必须由独立运维身份完成；
    schema DDL 必须通过 MIGRATION_DATABASE_URL 运行 Migration Runner。
    即使遗留调用点尚未被发现，也必须 fail-closed，不能回退使用应用 DSN。
    """
    raise RuntimeError(
        "禁止通过应用数据库连接创建数据库；"
        "请使用独立 provisioning 身份创建数据库，"
        "并使用 MIGRATION_DATABASE_URL 执行 python -m app.db.migrations apply"
    )
