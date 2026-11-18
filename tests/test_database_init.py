"""数据库启动初始化的并发与失败语义测试。"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.core import database as database_module


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return self

    def first(self):
        return self.value


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


class _RacingSession:
    def __init__(self, *, admin_after_race):
        self.admin_after_race = admin_after_race
        self.added = []
        self.execute_count = 0
        self.rollback_called = False

    async def execute(self, statement):
        self.execute_count += 1
        if self.execute_count == 1:
            return _ScalarResult(None)
        return _ScalarResult(self.admin_after_race)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        raise IntegrityError(
            "INSERT INTO users",
            {},
            Exception("Duplicate entry for key 'uq_users_username'"),
        )

    async def rollback(self):
        self.rollback_called = True


@pytest.mark.asyncio
async def test_init_db_accepts_admin_created_by_another_worker(monkeypatch):
    """并发 worker 唯一键竞争后，回滚并确认管理员已存在，不误判启动失败。"""
    session = _RacingSession(admin_after_race=object())
    monkeypatch.setattr(database_module, "AsyncSessionLocal", lambda: _SessionContext(session))
    monkeypatch.setattr(database_module.settings, "FIRST_SUPERUSER", "ci-admin")
    monkeypatch.setattr(database_module.settings, "FIRST_SUPERUSER_PASSWORD", "test-only-password")
    monkeypatch.setattr(
        database_module.User,
        "set_password",
        lambda self, password: setattr(self, "hashed_password", "test-hash"),
    )

    await database_module.init_db()

    assert len(session.added) == 1
    assert session.rollback_called is True
    assert session.execute_count == 2


@pytest.mark.asyncio
async def test_init_db_does_not_swallow_non_duplicate_integrity_error(monkeypatch):
    """非重复键完整性错误不能被误认为其它 worker 已创建管理员。"""
    session = _RacingSession(admin_after_race=None)

    async def fail_with_non_duplicate(self):
        raise IntegrityError(
            "INSERT INTO users",
            {},
            Exception("NOT NULL constraint failed: users.username"),
        )

    session.commit = fail_with_non_duplicate.__get__(session, _RacingSession)
    monkeypatch.setattr(database_module, "AsyncSessionLocal", lambda: _SessionContext(session))
    monkeypatch.setattr(database_module.settings, "FIRST_SUPERUSER", "ci-admin")
    monkeypatch.setattr(database_module.settings, "FIRST_SUPERUSER_PASSWORD", "test-only-password")
    monkeypatch.setattr(
        database_module.User,
        "set_password",
        lambda self, password: setattr(self, "hashed_password", "test-hash"),
    )

    with pytest.raises(IntegrityError):
        await database_module.init_db()

    assert session.rollback_called is True
    assert session.execute_count == 1
