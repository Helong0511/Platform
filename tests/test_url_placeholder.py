"""统一占位符模块测试。"""
import os
import sys

os.environ.setdefault("UNIT_TEST", "1")

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.url.placeholder import (
    normalize_placeholder_name,
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


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
