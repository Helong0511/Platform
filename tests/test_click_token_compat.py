"""
click_id 追踪令牌：向后兼容与开关行为测试。

运行方式（推荐）:
    python -m pytest tests/test_click_token_compat.py -v
"""
import os
import sys

os.environ.setdefault("UNIT_TEST", "1")
os.environ.setdefault("PRODUCTION_ENV", "development")

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from app.core.tracking.ad_tracking_codec import AdTrackingCodec
from app.core.tracking.click_token import (
    association_from_parsed,
    generate_click_id_unified,
    resolve_click_from_token,
    use_tracking_token,
)
from app.core.tracking.click_id_generator import generate_click_id_from_timestamp


def test_legacy_click_id_still_generated_when_flag_off(monkeypatch):
    monkeypatch.delenv("USE_TRACKING_TOKEN", raising=False)
    from app.core import config

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", False, raising=False)

    legacy = generate_click_id_unified(offer_id=1, publisher_id=2, advertiser_id=3)
    old_style = generate_click_id_from_timestamp()
    assert legacy == old_style or len(legacy) > 20
    assert resolve_click_from_token(legacy) is None


def test_tracking_token_roundtrip_when_flag_on(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.setattr(config.settings, "TRACKING_TOKEN_MAX_AGE_SECONDS", None, raising=False)

    token = generate_click_id_unified(
        offer_id=101,
        publisher_id=202,
        advertiser_id=303,
        short_link_id=9,
        url_params={"sub1": "abc", "fbclid": "x"},
    )
    assert use_tracking_token()

    assoc = resolve_click_from_token(token)
    assert assoc is not None
    assert assoc["offer_id"] == 101
    assert assoc["publisher_id"] == 202
    assert assoc["advertiser_id"] == 303
    assert assoc["short_link_id"] == 9
    assert assoc["url_params"].get("sub1") == "abc"
    assert assoc.get("_from_token") is True


def test_old_random_click_id_fails_token_parse():
    old_id = generate_click_id_from_timestamp()
    # 旧 ID 可能含非 58 字符集字符，或解析签名失败
    assert resolve_click_from_token(old_id) is None


def test_token_fits_click_id_max_length():
    from app.core.tracking.click_token import CLICK_ID_MAX_LENGTH

    token = AdTrackingCodec.generate(
        {"oid": 1, "pub": 2, "aid": 3, "up": {"sub1": "x"}},
        format="auto",
        max_outer_chars=255,
    )
    assert len(token) <= CLICK_ID_MAX_LENGTH


def test_codec_parse_structure():
    token = AdTrackingCodec.generate(
        {"oid": 1, "pub": 2, "aid": 3},
        format="auto",
        max_outer_chars=255,
    )
    parsed = AdTrackingCodec.parse(token)
    assert parsed["valid"] is True
    assoc = association_from_parsed(parsed)
    assert assoc["offer_id"] == 1
    assert assoc["publisher_id"] == 2
    assert assoc["advertiser_id"] == 3


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
