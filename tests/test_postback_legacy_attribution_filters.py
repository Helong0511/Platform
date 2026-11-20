"""Postback 归因筛选需兼容快照缺失的历史转化记录。"""
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mysql

from app.models.models import Click, PostbackConversion
from app.services.cpl.postback_conversion_service import (
    _snapshot_or_legacy_click_filter,
)


@pytest.mark.parametrize(
    ("snapshot_column", "click_column", "value", "column_name"),
    [
        (PostbackConversion.offer_id, Click.offer_id, 101, "offer_id"),
        (PostbackConversion.publisher_id, Click.publisher_id, 202, "publisher_id"),
        (PostbackConversion.advertiser_id, Click.advertiser_id, 303, "advertiser_id"),
    ],
)
def test_attribution_filter_includes_legacy_click_fallback(
    snapshot_column, click_column, value, column_name
):
    statement = select(PostbackConversion.id).where(
        _snapshot_or_legacy_click_filter(snapshot_column, click_column, value)
    )
    sql = str(
        statement.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert f"postback_conversions.{column_name} = {value}" in sql
    assert f"postback_conversions.{column_name} IS NULL" in sql
    assert "EXISTS (SELECT 1 FROM clicks" in sql
    assert f"clicks.{column_name} = {value}" in sql
    assert "clicks.click_id = postback_conversions.click_id" in sql
