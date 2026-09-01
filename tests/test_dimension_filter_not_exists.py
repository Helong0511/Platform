"""维度互斥选源：NOT EXISTS 形态与默认 TTL。"""
from __future__ import annotations

from datetime import date

from sqlalchemy.dialects import mysql

from app.models.models import AdData
from app.services.ad_data.queries.dimension_filter import (
    _outer_row_not_in_country_only_product_dates,
    kpi_mutual_source_filter,
)
from app.services.ad_data.query_cache import (
    ad_data_daily_summary_cache_ttl,
    ad_data_filter_options_cache_ttl,
    ad_data_summary_cache_ttl,
)


def _compile(clause) -> str:
    return str(
        clause.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_mutual_source_filter_uses_not_exists_not_tuple_not_in():
    clause = kpi_mutual_source_filter(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )
    sql = _compile(clause)
    assert "EXISTS" in sql.upper()
    assert "NOT IN" not in sql.upper()


def test_country_only_exclusion_uses_not_exists():
    clause = _outer_row_not_in_country_only_product_dates(
        AdData,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )
    sql = _compile(clause)
    assert "EXISTS" in sql.upper()
    assert "NOT IN" not in sql.upper()


def test_ad_data_cache_ttl_defaults():
    assert ad_data_daily_summary_cache_ttl() == 600
    assert ad_data_filter_options_cache_ttl() == 600
    assert ad_data_summary_cache_ttl() == 300
