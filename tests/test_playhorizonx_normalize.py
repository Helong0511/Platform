"""PlayHorizonx cross 规范化单元测试。运行：pytest tests/test_playhorizonx_normalize.py -q"""
from app.core.ad_data_metadata import REPORT_TYPE_CROSS, REPORT_TYPE_UNIT
from app.scheduler_module.playhorizonx_normalize import normalize_playhorizonx_rows

SAMPLE = {
    "date": "2026-08-23",
    "url": "https://free.playhorizonx.com/",
    "com_name": "SGSUO160",
    "country_code": "CN",
    "requests": "1",
    "matched_queries": "0",
    "viewsCount": "0",
    "clicks": "0",
    "channel_revenue": 0,
}


def test_cross_keeps_country_and_ad_unit():
    rows, stats = normalize_playhorizonx_rows([SAMPLE], report_type=REPORT_TYPE_CROSS)
    assert stats.kept_rows == 1
    assert rows[0]["country_code"] == "CN"
    assert rows[0]["com_name"] == "SGSUO160"
    assert rows[0]["url"] == "https://free.playhorizonx.com/"


def test_cross_skips_missing_country():
    bad = {**SAMPLE, "country_code": ""}
    rows, stats = normalize_playhorizonx_rows([bad], report_type=REPORT_TYPE_CROSS)
    assert rows == []
    assert stats.dropped_invalid_cross_shape == 1


def test_cross_skips_zz_country():
    bad = {**SAMPLE, "country_code": "ZZ"}
    rows, stats = normalize_playhorizonx_rows([bad], report_type=REPORT_TYPE_CROSS)
    assert rows == []
    assert stats.dropped_invalid_cross_shape == 1


def test_cross_skips_missing_ad_unit():
    bad = {**SAMPLE, "com_name": "0"}
    rows, stats = normalize_playhorizonx_rows([bad], report_type=REPORT_TYPE_CROSS)
    assert rows == []
    assert stats.dropped_invalid_cross_shape == 1


def test_unit_strips_country():
    rows, stats = normalize_playhorizonx_rows([SAMPLE], report_type=REPORT_TYPE_UNIT)
    assert stats.kept_rows == 1
    assert "country_code" not in rows[0]
    assert rows[0]["com_name"] == "SGSUO160"


def test_cross_skips_invalid_date():
    bad = {**SAMPLE, "date": "2026/08/23"}
    rows, stats = normalize_playhorizonx_rows([bad], report_type=REPORT_TYPE_CROSS)
    assert rows == []
    assert stats.dropped_missing_required == 1
