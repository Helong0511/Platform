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


@pytest.mark.asyncio
async def test_log_user_action_strict_mode_propagates_audit_enqueue_failure():
    from types import SimpleNamespace

    from app.core.audit_log import log_user_action

    class FakeDB:
        def add(self, _record):
            raise RuntimeError("simulated audit enqueue failure")

    user = SimpleNamespace(id=7, username="admin")
    db = FakeDB()

    # 默认模式维持非关键审计场景的历史容错行为。
    await log_user_action(
        db=db,
        action_type="CREATE",
        user=user,
        resource_type="TEST",
        strict=False,
    )

    # Cap 等关键变更必须保证审计记录能够加入同一事务。
    with pytest.raises(RuntimeError, match="simulated audit enqueue failure"):
        await log_user_action(
            db=db,
            action_type="CREATE",
            user=user,
            resource_type="TEST",
            strict=True,
        )
