"""Excel 导入真实 MySQL SAVEPOINT 集成测试。

只允许 GitHub Actions 提供的 loopback 临时 MySQL platform_ci；
使用独立随机数据库，验证行级回滚是真实数据库事务，而非 fake SAVEPOINT。
"""
import ipaddress
import os
import uuid
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import quote_plus

import pandas as pd
import pymysql
import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api_v1.excel.ad_data_import import row_processor


MYSQL_HOST = os.getenv("MYSQL_INTEGRATION_HOST")
MYSQL_PORT = int(os.getenv("MYSQL_INTEGRATION_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_INTEGRATION_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_INTEGRATION_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci")


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host.strip().lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip()).is_loopback
    except ValueError:
        return False


_SAFE_MYSQL_TARGET = (
    os.getenv("UNIT_TEST") == "1"
    and os.getenv("GITHUB_ACTIONS") == "true"
    and os.getenv("MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"
    and _is_loopback_host(MYSQL_HOST)
    and MYSQL_DATABASE == "platform_ci"
)

if (
    os.getenv("GITHUB_ACTIONS") == "true"
    or (os.getenv("UNIT_TEST") == "1" and MYSQL_HOST)
) and not _SAFE_MYSQL_TARGET:
    raise RuntimeError(
        "拒绝执行 Excel MySQL 集成测试：仅允许 loopback MySQL platform_ci，"
        "并显式启用 MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS=1"
    )

pytestmark = pytest.mark.skipif(
    not _SAFE_MYSQL_TARGET,
    reason="仅在 GitHub Actions 临时 MySQL platform_ci 服务中运行",
)


def _admin_connection():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        autocommit=True,
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=20,
        write_timeout=10,
    )


def _create_isolated_database() -> str:
    database = f"platform_ci_excel_{uuid.uuid4().hex[:16]}"
    connection = _admin_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()
    return database


def _drop_isolated_database(database: str) -> None:
    connection = _admin_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION lock_wait_timeout = 10")
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_mysql_excel_row_savepoint_rolls_back_real_database_side_effect(monkeypatch):
    """产品解析阶段已写库、后续指标校验失败时，MySQL 必须回滚该行写入。"""
    database = _create_isolated_database()
    engine = None
    try:
        user = quote_plus(MYSQL_USER)
        password = quote_plus(MYSQL_PASSWORD)
        engine = create_async_engine(
            f"mysql+aiomysql://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{database}"
            "?charset=utf8mb4",
            pool_pre_ping=True,
        )

        metadata = MetaData()
        side_effects = Table(
            "excel_row_side_effects",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("product_name", String(120), nullable=False),
        )
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
        product_info = {
            "product_id": 901,
            "client_id": 77,
            "client_name": "CI Client",
            "product_name": "invalid-metric-product",
            "ecpm_deduct_ratio": 0.0,
            "revenue_deduct_ratio": 0.0,
        }

        async def create_product_side_effect(**kwargs):
            # 模拟真实产品解析器：先执行 INSERT，再返回产品信息；
            # 后续数值校验失败时，该 INSERT 必须位于当前行 SAVEPOINT 内。
            await kwargs["db"].execute(
                side_effects.insert().values(product_name=product_info["product_name"])
            )
            kwargs["product_map"]["77_invalid-metric-product"] = product_info
            kwargs["product_name_map"]["invalid-metric-product"] = [product_info]
            return product_info

        monkeypatch.setattr(
            row_processor, "find_or_create_product", create_product_side_effect
        )

        product_map = {}
        product_name_map = {}
        existing_records = {}
        result = {
            "success_rows": 0,
            "failed_rows": 0,
            "new_rows": 0,
            "updated_rows": 0,
            "errors": [],
        }

        async with session_factory() as session:
            row = pd.Series({
                "date": datetime(2026, 11, 18),
                "product_name": "invalid-metric-product",
                "request_count": "not-a-number",
                "match_count": 0,
                "display_count": 0,
                "click_count": 0,
                "revenue_before_deduct": 0,
            })
            await row_processor.process_row_data(
                row=row,
                row_num=2,
                product_map=product_map,
                product_name_map=product_name_map,
                mapping_complete=True,
                client_id=None,
                db=session,
                current_user=SimpleNamespace(username="excel-mysql-ci"),
                result=result,
                existing_records=existing_records,
            )

            # SAVEPOINT 已回滚，但外层事务仍可正常提交，验证回滚范围仅限失败行。
            await session.commit()
            remaining = await session.scalar(
                select(side_effects.c.id).limit(1)
            )

        assert remaining is None
        assert product_map == {}
        assert product_name_map == {}
        assert result["success_rows"] == 0
        assert result["failed_rows"] == 1
        assert result["new_rows"] == 0
        assert result["updated_rows"] == 0
        assert result["errors"][0]["row"] == 2
        assert "数值字段格式错误" in result["errors"][0]["error"]
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)
