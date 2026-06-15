"""Alembic 环境配置（同步 pymysql，避免 aiomysql 不支持 URL 查询参数）。"""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection, make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.models.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def normalize_migration_url(url: str) -> str:
    """转为 Alembic 可用的同步 MySQL URL，移除驱动不支持的连接参数。"""
    if "+aiomysql" in url:
        url = url.replace("+aiomysql", "+pymysql")
    elif "+asyncmy" in url:
        url = url.replace("+asyncmy", "+pymysql")

    parsed = make_url(url)
    if "collation" in parsed.query:
        query = {key: value for key, value in parsed.query.items() if key != "collation"}
        parsed = parsed.set(query=query)
    return parsed.render_as_string(hide_password=False)


def get_url() -> str:
    raw = os.getenv("DATABASE_URL") or str(settings.SQLALCHEMY_DATABASE_URI)
    return normalize_migration_url(raw)


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        do_run_migrations(connection)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
