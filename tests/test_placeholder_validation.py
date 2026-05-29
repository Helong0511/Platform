"""占位符录入校验测试。"""
import os
import sys

os.environ.setdefault("UNIT_TEST", "1")

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.url.placeholder_validation import validate_track_url_placeholders


def test_valid_single_and_double_brace():
    url = "https://adv.com/click?cid={click_id}&cid2={{click_id}}&oid={offer_id}"
    r = validate_track_url_placeholders(url, offer_id=1)
    assert r.ok
    assert "click_id" in r.placeholders
    assert "offer_id" in r.placeholders


def test_unknown_placeholder_rejected():
    r = validate_track_url_placeholders("https://x.com?a={foobar}")
    assert not r.ok
    assert any("foobar" in e for e in r.errors)


def test_malformed_brace_rejected():
    r = validate_track_url_placeholders("https://x.com?a={click@id}")
    assert not r.ok
    assert r.errors

def test_unclosed_brace_rejected():
    r = validate_track_url_placeholders("https://x.com?a={click_id")
    assert not r.ok
    assert any("无法解析" in e for e in r.errors)


def test_hyphen_alias_normalized_to_click_id():
    """连字符写法与 click_id 等价（广告平台常见）。"""
    r = validate_track_url_placeholders("https://x.com?a={click-id}")
    assert r.ok


def test_triple_brace_rejected():
    r = validate_track_url_placeholders("https://x.com?a={{{click_id}}}")
    assert not r.ok
    assert any("三层" in e or "层数" in e for e in r.errors)


def test_alias_clickid_accepted():
    r = validate_track_url_placeholders("https://x.com?a={clickId}&b={sub_affid}")
    assert r.ok


def test_offer_tracklink_skips_association_warning():
    r = validate_track_url_placeholders(
        "https://x.com?oid={offer_id}",
        skip_association_warnings=True,
    )
    assert r.ok
    assert not r.warnings


def test_short_link_warns_without_offer():
    r = validate_track_url_placeholders("https://x.com?oid={offer_id}")
    assert r.ok
    assert r.warnings


def test_payout_alias_accepted():
    r = validate_track_url_placeholders("https://x.com?po={payout}")
    assert r.ok


def test_ad_platform_macros_accepted():
    url = (
        "https://x.com?gaid={GAID}&idfa={IDFA}"
        "&ip={CLIENT IP}&ua={CLIENT USER AGENT}&lang={CLIENT LANGUAGE}"
    )
    r = validate_track_url_placeholders(url, skip_association_warnings=True)
    assert r.ok
    assert not r.errors


def test_postback_payout_and_macros_accepted():
    from app.core.validation import validate_postback_url_placeholders

    ok, err = validate_postback_url_placeholders(
        "https://pub.com/pb?payout={payout}&cid={clickId}"
        "&gaid={GAID}&ip={CLIENT IP}"
    )
    assert ok, err


def test_postback_unknown_placeholder_rejected():
    from app.core.validation import validate_postback_url_placeholders

    ok, err = validate_postback_url_placeholders(
        "https://pub.com/pb?x={publisher_email}"
    )
    assert not ok
    assert err and "publisher_email" in err


def test_postback_resolve_second_pass_client_ip():
    from app.core.url.placeholder import resolve_brace_placeholders

    url = "https://pub.com/pb?ip={CLIENT IP}&p={payout}"
    data = {"ip": "1.2.3.4", "payout": "9.99", "url_params": {}}
    out = resolve_brace_placeholders(url, data)
    assert "1.2.3.4" in out
    assert "9.99" in out
    assert "{" not in out or "{CLIENT" not in out


def test_offer_response_skips_placeholder_validation():
    """读取 Offer 时不应因历史 tracklink 占位符阻断列表接口。"""
    from datetime import datetime, timezone
    from app.schemas.cpl.offer import OfferResponse

    offer = OfferResponse.model_validate(
        {
            "id": 1,
            "offer_name": "test",
            "advertiser_id": 1,
            "status": "Active",
            "postback_method": "GET",
            "is_active": True,
            "advertiser_tracklink": "https://x.com?x={UNKNOWN_MACRO}",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )
    assert "{UNKNOWN_MACRO}" in (offer.advertiser_tracklink or "")
