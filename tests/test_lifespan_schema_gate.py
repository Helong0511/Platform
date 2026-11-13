"""应用 lifespan schema gate：只读校验，不允许 worker 隐式创建数据库或表。"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.bootstrap import lifespan


class _FakeConnection:
    def __init__(self, drift):
        self.drift = drift
        self.sync_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def run_sync(self, callback):
        self.sync_calls.append(callback)
        return self.drift


class _FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self.connection


@pytest.mark.asyncio
async def test_lifespan_schema_verification_uses_read_only_gate(monkeypatch):
    connection = _FakeConnection(
        {"missing_tables": [], "missing_columns": {}}
    )
    engine = _FakeEngine(connection)
    gate_calls = []

    async def fake_gate(actual_connection):
        gate_calls.append(actual_connection)
        return "20261113_latest"

    monkeypatch.setattr(lifespan, "engine", engine)
    monkeypatch.setattr(lifespan, "verify_schema_revision", fake_gate)

    revision = await lifespan._verify_database_schema()

    assert revision == "20261113_latest"
    assert gate_calls == [connection]
    assert connection.sync_calls == [lifespan._schema_metadata_drift]


@pytest.mark.asyncio
async def test_lifespan_schema_verification_fails_on_missing_orm_objects(monkeypatch):
    connection = _FakeConnection(
        {
            "missing_tables": ["required_table"],
            "missing_columns": {"another_table": ["required_column"]},
        }
    )

    async def fake_gate(_connection):
        return "20261113_latest"

    monkeypatch.setattr(lifespan, "engine", _FakeEngine(connection))
    monkeypatch.setattr(lifespan, "verify_schema_revision", fake_gate)

    with pytest.raises(RuntimeError, match="数据库 schema 与 ORM 不一致"):
        await lifespan._verify_database_schema()


def test_lifespan_module_has_no_implicit_schema_ddl_calls():
    source_path = Path(lifespan.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "create_database":
            forbidden.append("create_database")
        elif isinstance(func, ast.Attribute) and func.attr == "create_all":
            forbidden.append("Base.metadata.create_all")
    assert forbidden == []
