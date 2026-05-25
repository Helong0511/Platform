"""
click_id 生成与解析往返测试。
"""
import pytest

# 测试使用独立密钥，避免依赖 .env
_TEST_KEY_HEX = "a" * 64


@pytest.fixture(autouse=True)
def _tracking_key_env(monkeypatch):
    monkeypatch.setenv("AD_TRACKING_MASTER_KEY_HEX", _TEST_KEY_HEX)
    monkeypatch.setenv("USE_TRACKING_TOKEN", "true")


def test_short_link_token_within_255_with_url_params():
    from app.core.tracking.click_token import (
        CLICK_ID_MAX_LENGTH,
        generate_tracking_click_id,
        resolve_click_from_token,
    )

    token = generate_tracking_click_id(
        offer_id=1,
        publisher_id=2,
        advertiser_id=3,
        short_link_id=99,
        url_params={"fbclid": "test123", "utm_source": "short"},
        for_short_link=True,
    )
    assert len(token) <= CLICK_ID_MAX_LENGTH
    assoc = resolve_click_from_token(token)
    assert assoc is not None
    assert assoc["offer_id"] == 1
    assert assoc["publisher_id"] == 2
    assert assoc["advertiser_id"] == 3
    assert assoc["short_link_id"] == 99
    assert assoc.get("url_params", {}).get("fbclid") == "test123"


def test_normal_token_roundtrip_with_url_params():
    from app.core.tracking.click_token import (
        CLICK_ID_MAX_LENGTH,
        generate_tracking_click_id,
        resolve_click_from_token,
    )

    token = generate_tracking_click_id(
        offer_id=10,
        publisher_id=20,
        advertiser_id=30,
        url_params={"fbclid": "abc"},
        for_short_link=False,
    )
    assert len(token) <= CLICK_ID_MAX_LENGTH
    assoc = resolve_click_from_token(token)
    assert assoc is not None
    assert assoc["offer_id"] == 10
    assert assoc.get("url_params", {}).get("fbclid") == "abc"


def test_legacy_click_id_skips_token_parse():
    from app.core.tracking.click_id_generator import generate_click_id_from_timestamp
    from app.core.tracking.click_token import (
        _looks_like_tracking_token,
        resolve_click_from_token,
    )

    legacy = generate_click_id_from_timestamp()
    assert 36 <= len(legacy) <= 52
    assert _looks_like_tracking_token(legacy) is False
    assert resolve_click_from_token(legacy) is None


def test_codec_rejects_full_when_outer_cap_60():
    from app.core.tracking.ad_tracking_codec import AdTrackingCodec

    big = {"oid": 1, "pub": 2, "aid": 3, "note": "x" * 200}
    with pytest.raises(ValueError):
        AdTrackingCodec.generate(
            big,
            format="auto",
            max_outer_chars=60,
            allow_full=False,
        )


def test_minimal_id_list_encoding():
    from app.core.tracking.click_token import (
        CLICK_ID_MAX_LENGTH,
        _KEY_ID_LIST,
        association_from_parsed,
        build_minimal_id_list_params,
    )
    from app.core.tracking.ad_tracking_codec import AdTrackingCodec, REASON_OK

    params = build_minimal_id_list_params(
        offer_id=5, publisher_id=6, advertiser_id=7, short_link_id=8
    )
    assert _KEY_ID_LIST in params
    token = AdTrackingCodec.generate(
        params, format="compact", max_outer_chars=CLICK_ID_MAX_LENGTH
    )
    parsed = AdTrackingCodec.parse(token)
    assert parsed["valid"] and parsed["reason"] == REASON_OK
    assoc = association_from_parsed(parsed)
    assert assoc["offer_id"] == 5
    assert assoc["publisher_id"] == 6
    assert assoc["advertiser_id"] == 7
    assert assoc["short_link_id"] == 8


def test_regenerate_includes_url_params():
    from app.core.tracking.click_token import (
        CLICK_ID_MAX_LENGTH,
        regenerate_click_id_from_click_data,
        resolve_click_from_token,
    )

    new_id = regenerate_click_id_from_click_data(
        {
            "offer_id": 1,
            "publisher_id": 2,
            "advertiser_id": 3,
            "short_link_id": 42,
            "url_params": {"sub": "aff1"},
        }
    )
    assert len(new_id) <= CLICK_ID_MAX_LENGTH
    assoc = resolve_click_from_token(new_id)
    assert assoc is not None
    assert assoc.get("url_params", {}).get("sub") == "aff1"


def test_normalizer_extracts_cid():
    from app.core.postback.transformers.normalizer import DataNormalizer

    out = DataNormalizer.normalize({"cid": "abc123"}, "generic")
    assert out["click_id"] == "abc123"
    assert out["conversion_id"] == "abc123"


def test_large_url_params_still_tries_to_keep_tracking_keys():
    from app.core.tracking.click_token import (
        CLICK_ID_MAX_LENGTH,
        generate_tracking_click_id,
        resolve_click_from_token,
    )

    huge = {f"k{i}": "v" * 500 for i in range(50)}
    huge["fbclid"] = "fb_important_123"
    token = generate_tracking_click_id(
        offer_id=1,
        publisher_id=2,
        advertiser_id=3,
        url_params=huge,
    )
    assert len(token) <= CLICK_ID_MAX_LENGTH
    assoc = resolve_click_from_token(token)
    assert assoc is not None
    assert assoc["offer_id"] == 1
    up = assoc.get("url_params") or {}
    # 尽量保留：至少应带上 fbclid（关键追踪键），而不是直接放弃全部 up
    assert up.get("fbclid") == "fb_important_123"


def test_two_phase_prefers_with_url_params():
    from app.core.tracking.click_token import (
        _KEY_URL_PARAMS,
        _build_generation_attempts,
    )

    attempts = _build_generation_attempts(
        offer_id=1,
        publisher_id=2,
        advertiser_id=3,
        short_link_id=None,
        url_params={"utm_source": "x"},
        extra=None,
    )
    first_with_up = next(
        (i for i, a in enumerate(attempts) if a and _KEY_URL_PARAMS in a),
        None,
    )
    first_without_up = next(
        (i for i, a in enumerate(attempts) if not a or _KEY_URL_PARAMS not in a),
        None,
    )
    assert first_with_up is not None
    assert first_without_up is not None
    assert first_with_up < first_without_up
