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


@pytest.mark.asyncio
async def test_client_error_logging_failure_does_not_expose_exception_text(monkeypatch, caplog):
    import logging

    from app.services import audit_log_service

    class FakeDB:
        def __init__(self):
            self.rollback_called = False

        async def rollback(self):
            self.rollback_called = True

    async def fail_with_sensitive_exception(**_kwargs):
        raise RuntimeError("private@example.com access_token=secret-value")

    db = FakeDB()
    monkeypatch.setattr(
        audit_log_service,
        "log_user_action",
        fail_with_sensitive_exception,
    )

    with caplog.at_level(logging.WARNING, logger="app.services.audit_log_service"):
        await audit_log_service.AuditLogService(db).log_client_error(
            error_type="TypeError",
            error_message="synthetic frontend error",
        )

    assert db.rollback_called is True
    assert "RuntimeError" in caplog.text
    assert "private@example.com" not in caplog.text
    assert "secret-value" not in caplog.text


def test_client_error_report_schema_enforces_bounded_json_fields():
    from pydantic import ValidationError

    from app.schemas.audit_log import ClientErrorReportRequest

    valid = ClientErrorReportRequest(
        error_type="TypeError",
        error_message="synthetic failure",
        error_stack="stack",
        error_url="https://example.invalid/app",
        user_agent="test-agent",
    )
    assert valid.error_type == "TypeError"

    with pytest.raises(ValidationError):
        ClientErrorReportRequest(
            error_type="TypeError",
            error_message="x" * 501,
        )

    with pytest.raises(ValidationError):
        ClientErrorReportRequest(
            error_type="TypeError",
            error_message="failure",
            error_stack="x" * 2001,
        )


def test_client_error_sanitizers_remove_query_credentials_and_pii():
    from app.services.audit_log_service import (
        _sanitize_client_error_text,
        _sanitize_client_error_url,
    )

    raw_url = 'https://example.invalid/error?access_token=secret&code=oauth-code#private-fragment'
    assert _sanitize_client_error_url(raw_url) == '/error'

    raw_text = 'failed for user@example.com Bearer abc.def token=secret-value password:pass123'
    sanitized = _sanitize_client_error_text(raw_text, 2000)
    assert 'user@example.com' not in sanitized
    assert 'abc.def' not in sanitized
    assert 'secret-value' not in sanitized
    assert 'pass123' not in sanitized
    assert '[REDACTED]' in sanitized


@pytest.mark.asyncio
async def test_log_user_action_recursively_redacts_nested_credentials():
    import json
    from types import SimpleNamespace

    from app.core.audit_log import log_user_action

    class FakeDB:
        def __init__(self):
            self.record = None

        def add(self, record):
            self.record = record

    db = FakeDB()
    await log_user_action(
        db=db,
        action_type='UPDATE',
        user=SimpleNamespace(id=9, username='operator'),
        resource_type='TEST',
        error_message='request failed token=inline-secret',
        request_params={
            'filters': {'refresh_token': 'nested-refresh', 'status': 'active'},
            'items': [{'Authorization': 'Bearer abc.def', 'name': 'safe'}],
        },
        details={
            'before': {'client_secret': 'nested-client-secret'},
            'after': [{'api_key': 'nested-api-key', 'enabled': True}],
            'note': 'Bearer xyz.123 was rejected',
        },
    )

    params = json.loads(db.record.request_params)
    details = json.loads(db.record.details)
    assert params['filters']['refresh_token'] == '[REDACTED]'
    assert params['items'][0]['Authorization'] == '[REDACTED]'
    assert params['items'][0]['name'] == 'safe'
    assert details['before']['client_secret'] == '[REDACTED]'
    assert details['after'][0]['api_key'] == '[REDACTED]'
    assert 'xyz.123' not in details['note']
    assert 'inline-secret' not in db.record.error_message
