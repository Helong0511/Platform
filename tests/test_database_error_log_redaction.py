"""数据库会话异常日志不得输出 SQL 参数或 Postback PII。"""
import logging

import pytest

from app.core import database


class _FakeDB:
    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def close(self):
        return None


class _SessionContext:
    async def __aenter__(self):
        return _FakeDB()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dependency_name",
    ["get_db", "get_postback_db", "get_db_readonly"],
)
async def test_database_dependency_logs_exception_type_without_raw_pii(
    dependency_name, monkeypatch, caplog
):
    sensitive_error = (
        "insert failed: buyer@example.invalid "
        "click_id=private-click ip=203.0.113.44"
    )
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _SessionContext())
    dependency = getattr(database, dependency_name)
    generator = dependency()

    yielded = await generator.__anext__()
    assert yielded is not None

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            await generator.athrow(RuntimeError(sensitive_error))

    assert "RuntimeError" in caplog.text
    assert sensitive_error not in caplog.text
    assert "buyer@example.invalid" not in caplog.text
    assert "private-click" not in caplog.text
    assert "203.0.113.44" not in caplog.text
