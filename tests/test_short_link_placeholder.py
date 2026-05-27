"""短链 /s、/change 占位符与 build_final_url 行为。"""
import os
import sys

os.environ.setdefault("UNIT_TEST", "1")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.routes.short_link.placeholder import replace_param_value_placeholders
from app.routes.short_link.url_builder import build_final_url


def test_replace_param_value_click_id():
    out, ok = replace_param_value_placeholders(
        "{click_id}",
        "CID99",
        10,
        20,
        30,
        {"ip": "1.2.3.4"},
    )
    assert ok is True
    assert "CID99" in out


def test_replace_param_value_offer_id_uses_resolved_pk():
    """build_final_url 应传入解析后的 Offer 主键，而非上游 offer 编号。"""
    out, ok = replace_param_value_placeholders(
        "oid={offer_id}",
        "x",
        145,
        None,
        None,
        {},
    )
    assert ok is True
    assert "145" in out


def test_build_final_url_merges_replaced_query_param():
    """用户 query 参数值含占位符且可替换时，会合并进最终 URL。"""
    before = "https://up.test/land?cid={click_id}"
    after = "https://up.test/land?cid=abc123"
    final = build_final_url(
        before,
        after,
        "RAWCLICK",
        final_offer_id=1,
        final_channel_id=2,
        request_params={"utm_campaign": "{click_id}"},
        request_info={"ip": "1.1.1.1"},
        advertiser_id=3,
    )
    assert "RAWCLICK" in final
    assert "utm_campaign" in final
    assert "{click_id}" not in final


def test_build_final_url_skips_plain_utm_not_in_template():
    before = "https://up.test/land?x={click_id}"
    after = "https://up.test/land?x=abc"
    final = build_final_url(
        before,
        after,
        "abc",
        final_offer_id=1,
        final_channel_id=2,
        request_params={"utm_source": "fb", "x": "{click_id}"},
        request_info={},
        advertiser_id=None,
    )
    assert "utm_source" not in final
    assert "abc" in final
