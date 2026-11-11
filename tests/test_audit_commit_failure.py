"""Audit transaction commit failures must reach the API caller."""
import pytest

from app.core.audit_log import commit_audit_log


@pytest.mark.asyncio
async def test_commit_audit_log_propagates_commit_error_after_rollback():
    class FakeDB:
        def __init__(self):
            self.rollback_called = False

        async def commit(self):
            raise RuntimeError("simulated commit failure")

        async def rollback(self):
            self.rollback_called = True

    db = FakeDB()

    with pytest.raises(RuntimeError, match="simulated commit failure"):
        await commit_audit_log(db)

    assert db.rollback_called is True


@pytest.mark.asyncio
async def test_commit_audit_log_returns_after_successful_commit():
    class FakeDB:
        def __init__(self):
            self.commit_called = False

        async def commit(self):
            self.commit_called = True

    db = FakeDB()

    await commit_audit_log(db)

    assert db.commit_called is True
