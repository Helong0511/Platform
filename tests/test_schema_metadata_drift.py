"""应用启动 schema drift 检查的隔离单元测试。"""

from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.bootstrap import lifespan as lifespan_module
from app.bootstrap.lifespan import _schema_metadata_drift


def test_schema_metadata_drift_reports_missing_tables_and_columns():
    metadata = MetaData()
    Table(
        "required_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("required_value", String(64), nullable=False),
    )
    Table(
        "another_required_table",
        metadata,
        Column("id", Integer, primary_key=True),
    )

    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE required_table (id INTEGER PRIMARY KEY)"
            )

        with engine.connect() as connection:
            drift = _schema_metadata_drift(connection, metadata)

        assert drift == {
            "missing_tables": ["another_required_table"],
            "missing_columns": {"required_table": ["required_value"]},
        }
    finally:
        engine.dispose()


def test_schema_metadata_drift_accepts_complete_existing_schema():
    metadata = MetaData()
    Table(
        "required_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("required_value", String(64), nullable=False),
    )

    engine = create_engine("sqlite:///:memory:")
    try:
        metadata.create_all(engine)
        with engine.connect() as connection:
            drift = _schema_metadata_drift(connection, metadata)

        assert drift == {"missing_tables": [], "missing_columns": {}}
    finally:
        engine.dispose()



@pytest.mark.asyncio
async def test_startup_schema_gate_is_read_only_and_rejects_missing_tables(monkeypatch):
    """API/Scheduler 启动只核验 schema，不得隐式创建 ORM 表。"""
    metadata = MetaData()
    Table(
        "required_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("required_value", String(64), nullable=False),
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(lifespan_module, "engine", engine)
    monkeypatch.setattr(
        lifespan_module, "Base", SimpleNamespace(metadata=metadata)
    )

    async def verified_revision(connection):
        return "ci-revision"

    monkeypatch.setattr(
        lifespan_module, "verify_schema_revision", verified_revision
    )
    try:
        with pytest.raises(RuntimeError, match="missing_tables"):
            await lifespan_module._verify_database_schema()

        async with engine.connect() as connection:
            existing_tables = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
        assert existing_tables == []
    finally:
        await engine.dispose()
