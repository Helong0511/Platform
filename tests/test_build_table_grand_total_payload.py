"""build_table_grand_total_payload 合计行 CPC 口径测试。"""
from app.services.ad_data.queries.summary_query import build_table_grand_total_payload


def _sample_raw():
    return {
        "total_requests": 100,
        "total_matches": 80,
        "total_displays": 60,
        "total_clicks": 10,
        "total_revenue_after": 5.0,
        "total_revenue_before": 20.0,
        "total_pageviews": 30,
        "weighted_viewability": 500.0,
        "viewability_weight": 10.0,
    }


def test_grand_total_cpc_always_uses_revenue_after_for_admin():
    """管理员合计 CPC 仍用扣后收益，与历史 fetch_grand_totals 一致。"""
    payload = build_table_grand_total_payload(raw=_sample_raw(), for_admin=True)
    assert payload["cpc"] == 0.5  # 5.0 / 10，而非 20.0 / 10


def test_grand_total_cpc_uses_revenue_after_for_client():
    payload = build_table_grand_total_payload(raw=_sample_raw(), for_admin=False)
    assert payload["cpc"] == 0.5
