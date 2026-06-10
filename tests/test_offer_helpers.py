"""
Offer helpers 单元测试（无数据库依赖部分）。
"""
import pytest
from fastapi import HTTPException

from app.core.errors import ErrorCode
from app.services.cpl.offer.helpers import (
    build_tracking_urls,
    extract_short_code_from_url,
    parse_publisher_configs,
)


def test_build_tracking_urls():
    downstream, postback = build_tracking_urls(42, "https://track.example.com/")
    assert "42" in downstream
    assert "{publisher_id}" in downstream
    assert "offer_id=42" in postback


def test_extract_short_code_from_url():
    assert extract_short_code_from_url("https://x.com/s/abc123?offer_id=1") == "abc123"
    assert extract_short_code_from_url("https://x.com/s/code/extra") == "code"
    assert extract_short_code_from_url("") is None


def test_parse_publisher_configs_rejects_duplicate():
    with pytest.raises(HTTPException) as exc_info:
        parse_publisher_configs([
            {"publisher_id": 1},
            {"publisher_id": 1},
        ])
    assert exc_info.value.detail["code"] == ErrorCode.INVALID_PARAMETER


def test_parse_publisher_configs_success():
    parsed = parse_publisher_configs([
        {"publisher_id": 2, "downstream_cap": 100, "affiliate_payout": 1.5},
    ])
    assert parsed == [(2, 100, 1.5)]
