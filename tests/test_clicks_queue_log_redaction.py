"""点击队列日志不得泄露原始载荷中的个人信息。"""
import pytest

from app.core import clicks_queue
from app.scheduler_module.tasks import clicks_batch_processor as processor


def test_invalid_click_payload_logs_fingerprint_without_payload(caplog):
    sensitive_payload = '{"ip":"203.0.113.55","user_agent":"PRIVATE-UA","referer":"https://private.example/path"'
    with caplog.at_level("WARNING", logger="app.core.clicks_queue"):
        assert clicks_queue._decode_click_payload(sensitive_payload) is None

    output = caplog.text
    assert "payload_sha256=" in output
    assert "payload_bytes=" in output
    assert "203.0.113.55" not in output
    assert "PRIVATE-UA" not in output
    assert "private.example" not in output


@pytest.mark.asyncio
async def test_dead_letter_log_uses_fingerprint_not_raw_payload(monkeypatch, caplog):
    sensitive_payload = '{"click_id":"private-click","ip":"203.0.113.56","user_agent":"PRIVATE-UA"}'

    class FakeRedis:
        async def eval(self, *args):
            return 1

    async def fake_redis():
        return FakeRedis()

    monkeypatch.setattr(clicks_queue, "get_redis_client", fake_redis)
    with caplog.at_level("ERROR", logger="app.core.clicks_queue"):
        assert await clicks_queue.move_to_dead_letter(sensitive_payload, "test_reason")

    output = caplog.text
    assert "payload_sha256=" in output
    assert "private-click" not in output
    assert "203.0.113.56" not in output
    assert "PRIVATE-UA" not in output


@pytest.mark.asyncio
async def test_click_database_exception_log_hides_exception_text_and_traceback(caplog):
    secret_parameter = "PRIVATE-CLICK-IP-198.51.100.77"

    class BrokenDB:
        async def execute(self, statement):
            raise RuntimeError(secret_parameter)

    click = {"click_id": "safe-test-id", "offer_id": 17}
    with caplog.at_level("ERROR", logger="app.scheduler_module.tasks.clicks_batch_processor"):
        with pytest.raises(RuntimeError, match=secret_parameter):
            await processor._validate_offer_ids(BrokenDB(), [click])

    assert secret_parameter not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "Traceback" not in caplog.text
