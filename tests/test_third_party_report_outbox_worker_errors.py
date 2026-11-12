"""第三方 Report Outbox 批量 Worker 异常隔离回归测试。"""
import logging

import pytest

from app.services import third_party_report_outbox as outbox


@pytest.mark.asyncio
async def test_batch_worker_counts_item_exception_without_masking_it(monkeypatch, caplog):
    """单条记录异常应计入 failed，不能因异常处理自身的 NameError 中断批次。"""

    class ScalarRows:
        def all(self):
            return [41]

    class QueryResult:
        def scalars(self):
            return ScalarRows()

    class FakeDB:
        async def execute(self, statement):
            return QueryResult()

        async def commit(self):
            return None

        async def scalar(self, statement):
            return 0

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    async def fail_one_item(report_log_id):
        assert report_log_id == 41
        raise RuntimeError("synthetic third-party failure")

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(outbox, "process_postback_report_outbox_item", fail_one_item)

    with caplog.at_level(logging.ERROR):
        result = await outbox.process_postback_report_outbox(batch_size=10)

    assert result == {
        "selected": 1,
        "success": 0,
        "retryable": 0,
        "failed": 1,
        "exhausted": 0,
        "terminal_failed": 0,
    }
    assert "error_type=RuntimeError" in caplog.text
    assert "synthetic third-party failure" not in caplog.text
