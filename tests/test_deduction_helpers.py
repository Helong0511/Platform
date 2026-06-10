"""
转化扣减 helpers / mappers 单元测试（无数据库依赖）。
"""
from unittest.mock import MagicMock

from app.services.cpl.deduction.helpers import (
    build_config_fields,
    resolve_config_level_target,
)
from app.services.cpl.deduction.mappers import config_to_export_row


def test_build_config_fields_offer_level():
    fields = build_config_fields(
        "offer",
        42,
        {"enable_volume_deduction": True, "volume_deduction_ratio": 0.1},
    )
    assert fields["offer_id"] == 42
    assert fields["advertiser_id"] is None
    assert fields["publisher_id"] is None
    assert fields["enable_volume_deduction"] is True


def test_resolve_config_level_target_publisher():
    config = MagicMock()
    config.advertiser_id = None
    config.offer_id = None
    config.publisher_id = 7
    level, target_id = resolve_config_level_target(config)
    assert level == "publisher"
    assert target_id == 7


def test_config_to_export_row_inactive_volume():
    config = MagicMock()
    config.id = 1
    config.advertiser = None
    config.offer = None
    config.publisher = MagicMock(publisher_name="测试渠道")
    config.enable_volume_deduction = False
    config.enable_amount_deduction = False
    config.volume_deduction_ratio = 0.0
    config.amount_deduction_ratio = 0.0
    config.deduction_strategy = "random"
    config.priority = 0
    config.is_active = False
    config.created_at = None
    config.updated_at = None

    row = config_to_export_row(config)
    assert row["配置层级"] == "渠道"
    assert row["配置对象"] == "测试渠道"
    assert row["扣量比例"] == "0%"
    assert row["状态"] == "禁用"
