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


@pytest.mark.asyncio
async def test_mysql_excel_mixed_rows_keep_successful_rows_and_rollback_only_failed_row(
    monkeypatch,
):
    """真实 MySQL 验证成功-失败-成功交错时只回滚失败行。"""
    from sqlalchemy import Boolean, Date, Numeric
    from sqlalchemy.orm import registry

    database = _create_isolated_database()
    engine = None
    mapper_registry = registry()
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
            "excel_mixed_row_side_effects",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("product_name", String(120), nullable=False),
        )
        ad_data_table = Table(
            "excel_ad_data_probe",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("date", Date, nullable=False),
            Column("country_code", String(100), nullable=True),
            Column("product_id", Integer, nullable=False),
            Column("ad_unit", String(150), nullable=False),
            Column("data_source", String(32), nullable=False),
            Column("report_type", String(16), nullable=False),
            Column("upstream_account", String(64), nullable=False, default="", server_default=""),
            Column("request_count", Integer, nullable=False),
            Column("match_count", Integer, nullable=False),
            Column("display_count", Integer, nullable=False),
            Column("click_count", Integer, nullable=False),
            Column("coverage_rate", Numeric(7, 4), nullable=False),
            Column("display_rate", Numeric(7, 4), nullable=False),
            Column("click_rate", Numeric(7, 4), nullable=False),
            Column("viewability_rate", Numeric(7, 4), nullable=False),
            Column("cpc", Numeric(12, 4), nullable=False),
            Column("pageviews", Integer, nullable=False),
            Column("ecpm_before_deduct", Numeric(12, 4), nullable=False),
            Column("ecpm_after_deduct", Numeric(12, 4), nullable=False),
            Column("revenue_before_deduct", Numeric(12, 4), nullable=False),
            Column("revenue_after_deduct", Numeric(12, 4), nullable=False),
            Column("is_deducted", Boolean, nullable=False, default=False),
        )

        class AdDataProbe:
            def finalize_metrics(self):
                self.is_deducted = False

        mapper_registry.map_imperatively(AdDataProbe, ad_data_table)

        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )

        async def create_product_side_effect(**kwargs):
            name = kwargs["product_name"]
            await kwargs["db"].execute(
                side_effects.insert().values(product_name=name)
            )
            info = {
                "product_id": 901,
                "client_id": 77,
                "client_name": "CI Client",
                "product_name": name,
                "ecpm_deduct_ratio": 0.0,
                "revenue_deduct_ratio": 0.0,
            }
            key = f"77_{name}"
            kwargs["product_map"][key] = info
            kwargs["product_name_map"][name] = [info]
            return info

        monkeypatch.setattr(
            row_processor, "find_or_create_product", create_product_side_effect
        )
        monkeypatch.setattr(row_processor, "AdData", AdDataProbe)

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

        def make_row(day: int, name: str, request_count):
            return pd.Series({
                "date": datetime(2026, 11, day),
                "product_name": name,
                "request_count": request_count,
                "match_count": 8,
                "display_count": 6,
                "click_count": 2,
                "revenue_before_deduct": 1.25,
            })

        async with session_factory() as session:
            for row_num, row in enumerate(
                [
                    make_row(18, "valid-before", 10),
                    make_row(19, "invalid-middle", "not-a-number"),
                    make_row(20, "valid-after", 12),
                ],
                start=2,
            ):
                await row_processor.process_row_data(
                    row=row,
                    row_num=row_num,
                    product_map=product_map,
                    product_name_map=product_name_map,
                    mapping_complete=True,
                    client_id=None,
                    db=session,
                    current_user=SimpleNamespace(username="excel-mysql-ci"),
                    result=result,
                    existing_records=existing_records,
                )

            # 外层事务提交后，前后两条成功行必须保留，中间失败行必须完全消失。
            await session.commit()
            side_effect_names = list(
                await session.scalars(
                    select(side_effects.c.product_name).order_by(side_effects.c.id)
                )
            )
            persisted_ad_data = list(
                await session.scalars(
                    select(ad_data_table.c.date).order_by(ad_data_table.c.date)
                )
            )

        assert side_effect_names == ["valid-before", "valid-after"]
        assert [value.day for value in persisted_ad_data] == [18, 20]
        assert result["success_rows"] == 2
        assert result["failed_rows"] == 1
        assert result["new_rows"] == 2
        assert result["updated_rows"] == 0
        assert result["errors"][0]["row"] == 3
        assert "数值字段格式错误" in result["errors"][0]["error"]
        assert "77_invalid-middle" not in product_map
        assert "invalid-middle" not in product_name_map
        assert "77_valid-before" in product_map
        assert "77_valid-after" in product_map
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)
        mapper_registry.dispose()
