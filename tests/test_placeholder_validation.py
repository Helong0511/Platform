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
    r = validate_track_url_placeholders("https://x.com?a={click-id}")
    assert not r.ok
    assert any("无法解析" in e for e in r.errors)


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
