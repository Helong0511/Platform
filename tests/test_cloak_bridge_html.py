"""斗篷桥页 HTML 注入单元测试。"""
import os
import sys

import pytest

os.environ.setdefault("UNIT_TEST", "1")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def test_cloak_meta_defaults():
    from app.routes.short_link.cloak_bridge_html import cloak_meta_from_row

    meta = cloak_meta_from_row(None, "master")
    assert meta["report_event"] == "ViewContent"
    assert meta["dp"] == "master"
    assert meta["load_report_enabled"] is False


def test_inject_meta_into_head():
    from app.routes.short_link.cloak_bridge_html import build_meta_snippet, inject_meta_into_html

    html = "<html><head></head><body></body></html>"
    out = inject_meta_into_html(html, build_meta_snippet({"dp": "x", "report_event": "ViewContent"}))
    assert "cloak-report-meta-b64" in out
    assert out.index("cloak-report-meta-b64") < out.index("<body>")


def test_append_load_report_inject():
    from app.routes.short_link.cloak_bridge_html import append_load_report_inject

    html = "<html><body></body></html>"
    out = append_load_report_inject(html)
    assert "DOMContentLoaded" in out or "cloak_load" in out.lower() or len(out) > len(html)


def test_sanitize_dp_rejects_invalid():
    from app.routes.short_link.cloak_bridge_html import sanitize_dp_param

    assert sanitize_dp_param("../etc") is None
    assert sanitize_dp_param("master-1") == "master-1"
