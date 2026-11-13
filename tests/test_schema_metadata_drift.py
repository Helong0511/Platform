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

        assert drift["missing_tables"] == ["another_required_table"]
        assert drift["missing_columns"] == {"required_table": ["required_value"]}
        assert drift["column_type_mismatches"] == {}
        assert drift["nullable_mismatches"] == {}
        assert drift["primary_key_mismatches"] == {}
        assert drift["index_mismatches"] == {}
        assert drift["unique_constraint_mismatches"] == {}
        assert drift["foreign_key_mismatches"] == {}
        assert drift["table_option_mismatches"] == {}
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

        assert drift == {
            "missing_tables": [],
            "missing_columns": {},
            "column_type_mismatches": {},
            "nullable_mismatches": {},
            "primary_key_mismatches": {},
            "index_mismatches": {},
            "unique_constraint_mismatches": {},
            "foreign_key_mismatches": {},
            "table_option_mismatches": {},
        }
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



def test_schema_metadata_drift_detects_type_nullability_and_primary_key_changes():
    metadata = MetaData()
    Table(
        "required_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("required_value", String(64), nullable=False),
    )

    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE required_table (id TEXT NOT NULL, required_value VARCHAR(32))"
            )
        with engine.connect() as connection:
            drift = _schema_metadata_drift(connection, metadata)

        assert drift["column_type_mismatches"] == {
            "required_table": {
                "id": {"expected": "INTEGER", "actual": "TEXT"},
                "required_value": {"expected": "VARCHAR(64)", "actual": "VARCHAR(32)"},
            }
        }
        assert drift["nullable_mismatches"] == {
            "required_table": {"required_value": {"expected": False, "actual": True}}
        }
        assert drift["primary_key_mismatches"] == {
            "required_table": {"expected": ["id"], "actual": []}
        }
    finally:
        engine.dispose()
