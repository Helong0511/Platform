"""第三方上报 HTTP 总时限测试。"""
import asyncio
import time

import pytest

from app.core import third_party_report


def test_http_total_deadline_is_shorter_than_report_lease():
    deadline = third_party_report._report_http_request_deadline_seconds()
    assert 0 < deadline < third_party_report.REPORT_LOG_LEASE_SECONDS


async def test_slow_trickling_http_response_is_cancelled_by_total_deadline(monkeypatch):
    """持续有数据活动的慢响应也不能无限延长租约占用。"""
    monkeypatch.setattr(
        third_party_report,
        "REPORT_HTTP_REQUEST_DEADLINE_SECONDS",
        0.05,
    )
    cancelled = asyncio.Event()

    class SlowTricklingClient:
        async def post(self, url, *, json, params):
            try:
                # 模拟每 10ms 就有进展的数据流；HTTPX read timeout 不会限制总时长。
                while True:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                cancelled.set()
                raise

    started = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        await third_party_report._post_with_total_deadline(
            SlowTricklingClient(),
            "https://mock.invalid/events",
            json={"data": []},
            params={},
        )

    assert time.monotonic() - started < 0.5
    assert cancelled.is_set()
