"""Postback 请求解析。"""
import os
import sys

import pytest

os.environ.setdefault("UNIT_TEST", "1")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.mark.asyncio
async def test_collect_query_params():
    from starlette.requests import Request

    from app.core.postback.request_parser import collect_postback_raw_data

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/postback",
        "headers": [],
        "query_string": b"clk_id=abc&payout=1.5",
    }
    request = Request(scope)
    data = await collect_postback_raw_data(request)
    assert data["clk_id"] == "abc"
    assert data["payout"] == "1.5"
