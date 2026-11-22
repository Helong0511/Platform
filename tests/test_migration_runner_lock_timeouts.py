"""Migration Runner metadata/row lock wait budget tests."""
from __future__ import annotations

import pytest

from app.db.migrations.runner import (
    MigrationRunnerError,
    _configure_migration_lock_timeouts,
)


class _Result:
    def __init__(self, values):
        self.values = values

    def mappings(self):
        return self

    def one(self):
        return self.values


class _Connection:
    def __init__(self, metadata_timeout=30, row_timeout=30):
        self.statements = []
        self.committed = False
        self.values = {
            "metadata_lock_wait_timeout": metadata_timeout,
            "innodb_lock_wait_timeout": row_timeout,
        }

    async def exec_driver_sql(self, statement):
        self.statements.append(statement)

    async def execute(self, statement):
        self.statements.append(str(statement))
        return _Result(self.values)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_migration_runner_sets_and_verifies_bounded_lock_waits():
    connection = _Connection()

    await _configure_migration_lock_timeouts(connection)

    assert "SET SESSION lock_wait_timeout = 30" in connection.statements
    assert "SET SESSION innodb_lock_wait_timeout = 30" in connection.statements
    assert "@@SESSION.lock_wait_timeout" in connection.statements[-1]
    assert connection.committed is True


@pytest.mark.asyncio
async def test_migration_runner_fails_closed_if_lock_wait_budget_did_not_apply():
    connection = _Connection(metadata_timeout=31536000, row_timeout=50)

    with pytest.raises(MigrationRunnerError, match='lock 等待超时'):
        await _configure_migration_lock_timeouts(connection)

    assert connection.committed is False