"""手动 Postback 补发必须报告真实转发结果，而非仅报告函数未抛异常。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.postback import forwarder
from app.core.postback.forwarder import PostbackForwarder
from app.models.models import UserRole
from app.services.notification.commands import resend_command


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalars(self):
        return self

    def first(self):
        return self.value

    def all(self):
        return self.value


class _DB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.statements = []
        self.added = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.results.pop(0))

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None


def _conversion(conversion_id=101):
    return SimpleNamespace(
        id=conversion_id,
        platform="test",
        click_id=None,
        payout=1,
        conversion_id=f"external-{conversion_id}",
        event_name="Purchase",
        event_value=1,
        ip="192.0.2.10",
        product_id=10,
    )


def _admin():
    return SimpleNamespace(id=1, role=UserRole.ADMIN)


@pytest.mark.asyncio
async def test_forwarder_returns_none_when_no_publisher_target_exists():
    result = await PostbackForwarder.forward_to_publisher(
        conversion=_conversion(),
        db=SimpleNamespace(),
    )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request_result", "check_result", "expected_success"),
    [
        ((True, 200, "ok"), (True, "accepted"), True),
        ((False, 502, "bad gateway"), (False, "rejected"), False),
    ],
)
async def test_forwarder_returns_persisted_log_for_attempted_request(
    monkeypatch,
    request_result,
    check_result,
    expected_success,
):
    publisher = SimpleNamespace(
        id=7,
        postback_url="https://publisher.invalid/callback",
        is_active=True,
        publisher_name="test-publisher",
        postback_method="GET",
        postback_success_check=None,
    )
    db = _DB()

    async def get_publisher(publisher_id, session):
        assert publisher_id == 7
        assert session is db
        return publisher

    async def send_request(**kwargs):
        return request_result

    async def no_op(**kwargs):
        return None

    monkeypatch.setattr(forwarder.CacheManager, "get_cached_publisher", get_publisher)
    monkeypatch.setattr(forwarder.PlaceholderResolver, "resolve", lambda url, data: url)
    monkeypatch.setattr(
        forwarder.UrlBuilder,
        "build_postback_url",
        lambda *args: (publisher.postback_url, {"conversion_id": "external"}),
    )
    monkeypatch.setattr(forwarder.HttpClient, "send_request", send_request)
    monkeypatch.setattr(forwarder.SuccessChecker, "check", lambda **kwargs: check_result)
    monkeypatch.setattr(PostbackForwarder, "_send_failure_notification", no_op)
    monkeypatch.setattr(PostbackForwarder, "_send_success_notification", no_op)
    monkeypatch.setattr(PostbackForwarder, "_enqueue_publisher_forward_retry", no_op)

    result = await PostbackForwarder.forward_to_publisher(
        conversion=_conversion(),
        db=db,
        target_publisher_id=7,
    )

    assert result is db.added[0]
    assert result.success is expected_success


@pytest.mark.asyncio
async def test_single_resend_reports_failed_downstream_result(monkeypatch):
    db = _DB([_conversion()])
    failed_log = SimpleNamespace(id=900, success=False)

    async def forward(**kwargs):
        return failed_log

    monkeypatch.setattr(resend_command.PostbackForwarder, "forward_to_publisher", forward)

    result = await resend_command.ResendNotificationCommand(db).resend_conversion(
        101,
        _admin(),
    )

    assert result["success"] is False
    assert result["forward_log_id"] == 900
    assert "未确认成功" in result["message"]


@pytest.mark.asyncio
async def test_single_resend_does_not_report_success_when_forwarder_skips(monkeypatch):
    db = _DB([_conversion()])

    async def forward(**kwargs):
        return None

    monkeypatch.setattr(resend_command.PostbackForwarder, "forward_to_publisher", forward)

    with pytest.raises(HTTPException):
        await resend_command.ResendNotificationCommand(db).resend_conversion(
            101,
            _admin(),
        )


@pytest.mark.asyncio
async def test_batch_resend_counts_only_confirmed_forward_logs_as_success(monkeypatch):
    conversions = [_conversion(1), _conversion(2), _conversion(3)]
    db = _DB([conversions])

    async def forward(*, conversion, db):
        if conversion.id == 1:
            return SimpleNamespace(id=901, success=True)
        if conversion.id == 2:
            return SimpleNamespace(id=902, success=False)
        return None

    monkeypatch.setattr(resend_command.PostbackForwarder, "forward_to_publisher", forward)

    result = await resend_command.ResendNotificationCommand(db).batch_resend_conversions(
        [1, 2, 3],
        _admin(),
    )

    assert result["success_count"] == 1
    assert result["failed_count"] == 2
    assert result["failed_items"][0]["forward_log_id"] == 902
    assert result["failed_items"][1]["conversion_id"] == 3
