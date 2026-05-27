"""统一占位符模块测试。"""
import os
import sys

os.environ.setdefault("UNIT_TEST", "1")

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.url.placeholder import (
    ANY_NAMED_PLACEHOLDER_RE,
    expand_brace_placeholder_variants,
    find_named_placeholders,
    normalize_placeholder_name,
    replace_placeholder_literals,
    resolve_brace_placeholders,
)


def test_normalize_clickid_alias():
    assert normalize_placeholder_name("clickId") == "click_id"


def test_resolve_brace_placeholders():
    url = "https://pub.test/pb?click_id={click_id}&payout={payout}"
    out = resolve_brace_placeholders(
        url,
        {"click_id": "ABC123", "payout": 1.5, "url_params": {}},
    )
    assert "ABC123" in out
    assert "1.5" in out
    assert "{" not in out


def test_find_named_placeholders_double_brace():
    from app.core.url.placeholder import find_named_placeholders

    assert find_named_placeholders("https://x.com?a={{click_id}}&b={offer_id}") == [
        "click_id",
        "offer_id",
    ]


def test_resolve_brace_placeholders_double_brace():
    url = "https://pub.test/pb?click_id={{click_id}}"
    out = resolve_brace_placeholders(
        url,
        {"click_id": "TOK1", "url_params": {}},
    )
    assert out == "https://pub.test/pb?click_id=TOK1"
    assert "{" not in out


def test_replace_param_value_double_brace():
    from app.routes.short_link.placeholder import replace_param_value_placeholders

    out, ok = replace_param_value_placeholders(
        "{{click_id}}",
        "CID1",
        1,
        2,
        3,
        {"ip": "1.1.1.1"},
    )
    assert ok is True
    assert out == "CID1"


def test_coexist_single_and_double_brace_same_url():
    from app.core.url.placeholder import find_named_placeholders, replace_placeholder_literals

    url = "https://x.com?a={click_id}&b={{click_id}}&c={offer_id}&d={{offer_id}}"
    names = find_named_placeholders(url)
    assert names == ["click_id", "offer_id"]

    out = url
    out = replace_placeholder_literals(out, "click_id", "CID")
    out = replace_placeholder_literals(out, "offer_id", "99")
    assert out == "https://x.com?a=CID&b=CID&c=99&d=99"
    assert "{" not in out


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
