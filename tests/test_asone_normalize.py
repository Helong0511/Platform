"""Asone 行规范化单元测试。运行：pytest tests/test_asone_normalize.py -q"""
from app.core.ad_data_metadata import (
    REPORT_TYPE_COUNTRY,
    REPORT_TYPE_CROSS,
    REPORT_TYPE_DAILY,
    REPORT_TYPE_UNIT,
)
from app.scheduler_module.asone_normalize import normalize_asone_rows

SAMPLE = {
    "id": 22703095,
    "reportDate": "2026-10-12",
    "domainName": "zxcv.poki.love",
    "country": "UNITED STATES",
    "unitId": "23378317340",
    "requests": 1,
    "matchedRequests": 1,
    "impressions": 0,
    "clicks": 0,
    "estimatedEarnings": 0.0,
}


def test_cross_maps_fields_and_country_alias():
    rows, stats = normalize_asone_rows([SAMPLE], report_type=REPORT_TYPE_CROSS)
    assert stats.kept_rows == 1
    row = rows[0]
    assert row["date"] == "2026-10-12"
    assert row["product_name"] == "zxcv.poki.love"
    assert row["country_code"] == "US"
    assert row["ad_unit"] == "23378317340"
    assert row["request_count"] == 1
    assert row["match_count"] == 1
    assert row["display_count"] == 0
    assert row["click_count"] == 0
    assert row["revenue_before_deduct"] == 0.0
    assert isinstance(row["request_count"], int)
    assert isinstance(row["revenue_before_deduct"], float)


def test_cross_coerces_string_metrics():
    raw = {
        **SAMPLE,
        "requests": "2",
        "matchedRequests": "2.0",
        "impressions": "3",
        "clicks": "1",
        "estimatedEarnings": "1.25",
        "ecpm": "4.5",
    }
    rows, _ = normalize_asone_rows([raw], report_type=REPORT_TYPE_CROSS)
    assert rows[0]["request_count"] == 2
    assert rows[0]["match_count"] == 2
    assert rows[0]["display_count"] == 3
    assert rows[0]["click_count"] == 1
    assert rows[0]["revenue_before_deduct"] == 1.25
    assert rows[0]["ecpm_before_deduct"] == 4.5


def test_cross_drops_missing_country_or_unit():
    bad_country = {**SAMPLE, "country": ""}
    bad_unit = {**SAMPLE, "unitId": ""}
    rows1, s1 = normalize_asone_rows([bad_country], report_type=REPORT_TYPE_CROSS)
    rows2, s2 = normalize_asone_rows([bad_unit], report_type=REPORT_TYPE_CROSS)
    assert rows1 == [] and s1.dropped_invalid_shape == 1
    assert rows2 == [] and s2.dropped_invalid_shape == 1


def test_country_strips_ad_unit():
    rows, _ = normalize_asone_rows([SAMPLE], report_type=REPORT_TYPE_COUNTRY)
    assert rows[0]["country_code"] == "US"
    assert rows[0]["ad_unit"] == ""


def test_unit_strips_country():
    rows, _ = normalize_asone_rows([SAMPLE], report_type=REPORT_TYPE_UNIT)
    assert rows[0]["ad_unit"] == "23378317340"
    assert rows[0]["country_code"] == ""


def test_daily_strips_country_and_unit():
    rows, _ = normalize_asone_rows([SAMPLE], report_type=REPORT_TYPE_DAILY)
    assert rows[0]["country_code"] == ""
    assert rows[0]["ad_unit"] == ""


def test_drops_invalid_date_or_domain():
    bad_date = {**SAMPLE, "reportDate": "2026/10/12"}
    bad_domain = {**SAMPLE, "domainName": ""}
    rows1, s1 = normalize_asone_rows([bad_date], report_type=REPORT_TYPE_CROSS)
    rows2, s2 = normalize_asone_rows([bad_domain], report_type=REPORT_TYPE_CROSS)
    assert rows1 == [] and s1.dropped_missing_required == 1
    assert rows2 == [] and s2.dropped_missing_required == 1
