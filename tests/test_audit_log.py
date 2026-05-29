"""审计日志模块单测"""
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.audit_log import (
    ALLOWED_ACTION_TYPES,
    commit_audit_log,
    log_login,
    log_user_action,
)


def test_allowed_action_types_includes_security_and_session_types():
    required = {
        "LOGIN", "LOGOUT", "CREATE", "UPDATE", "DELETE",
        "REVOKE_SESSION", "REVOKE_ALL_SESSIONS", "CSRF_VIOLATION",
        "RUNTIME_ERROR", "API_ACCESS", "TASK_RUN",
    }
    assert required.issubset(ALLOWED_ACTION_TYPES)


def test_log_user_action_accepts_user_agent_parameter():
    sig = inspect.signature(log_user_action)
    assert "user_agent" in sig.parameters


def test_log_login_supports_failure_without_user_object():
    sig = inspect.signature(log_login)
    assert sig.parameters["user"].default is None
    assert sig.parameters["username"].default is None
    assert sig.parameters["success"].default is True


@pytest.mark.asyncio
async def test_unknown_action_type_skips_persist():
    db = AsyncMock()
    await log_user_action(
        db=db,
        action_type="NOT_IN_WHITELIST",
        username="tester",
    )
    db.add.assert_not_called()
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_log_user_action_persists_with_user_agent():
    db = MagicMock()
    db.add = MagicMock()

    await log_user_action(
        db=db,
        action_type="RUNTIME_ERROR",
        username="guest",
        user_agent="TestAgent/1.0",
        success=False,
        error_message="err",
        resource_type="FRONTEND",
    )

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.action_type == "RUNTIME_ERROR"
    assert added.user_agent == "TestAgent/1.0"
    assert added.success is False


@pytest.mark.asyncio
async def test_commit_audit_log_calls_db_commit():
    db = AsyncMock()
    await commit_audit_log(db)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_log_login_with_username_only():
    db = MagicMock()
    db.add = MagicMock()
    request = MagicMock()
    request.headers = {}
    request.method = "POST"
    request.url.path = "/api/v1/auth/login"

    await log_login(
        db=db,
        request=request,
        username="unknown_user",
        success=False,
        error_message="用户名或密码不正确",
    )

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.action_type == "LOGIN"
    assert added.username == "unknown_user"
    assert added.success is False


def test_frontend_critical_action_types_in_whitelist():
    frontend_critical = {
        "REVOKE_SESSION", "REVOKE_ALL_SESSIONS", "CSRF_VIOLATION",
    }
    assert frontend_critical.issubset(ALLOWED_ACTION_TYPES)
