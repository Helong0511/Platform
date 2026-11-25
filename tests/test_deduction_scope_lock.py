"""扣量 scope 互斥锁的事务边界与排序测试。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.cpl.deduction.helpers import lock_deduction_scopes


class _LockResult:
    def scalar_one_or_none(self):
        return 1


@pytest.mark.asyncio
async def test_scope_locks_are_deduplicated_and_sorted_without_commit():
    db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="mysql")),
        execute=AsyncMock(return_value=_LockResult()),
        commit=AsyncMock(),
    )

    await lock_deduction_scopes(
        db,
        [
            ("publisher", 9),
            ("offer", 7),
            ("advertiser", 3),
            ("offer", 7),
        ],
    )

    assert db.execute.await_count == 6
    assert db.commit.await_count == 0
    insert_params = [
        call.args[1]
        for call in db.execute.await_args_list
        if "INSERT INTO conversion_deduction_scope_locks" in str(call.args[0])
    ]
    assert insert_params == [
        {"scope_type": "advertiser", "scope_id": 3},
        {"scope_type": "offer", "scope_id": 7},
        {"scope_type": "publisher", "scope_id": 9},
    ]


@pytest.mark.asyncio
async def test_scope_lock_rejects_unsupported_database_dialect():
    db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        execute=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="不支持当前数据库方言"):
        await lock_deduction_scopes(db, [("offer", 1)])

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_scope_lock_rejects_non_positive_ids():
    db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="mysql")),
        execute=AsyncMock(),
    )

    with pytest.raises(Exception):
        await lock_deduction_scopes(db, [("offer", 0)])

    db.execute.assert_not_awaited()
