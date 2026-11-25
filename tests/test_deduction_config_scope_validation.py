"""扣量配置 scope 完整性回归测试。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.cpl.deduction.helpers import resolve_config_level_target


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (SimpleNamespace(advertiser_id=11, offer_id=None, publisher_id=None), ("advertiser", 11)),
        (SimpleNamespace(advertiser_id=None, offer_id=22, publisher_id=None), ("offer", 22)),
        (SimpleNamespace(advertiser_id=None, offer_id=None, publisher_id=33), ("publisher", 33)),
    ],
)
def test_resolve_config_level_target_accepts_exactly_one_positive_scope(config, expected):
    assert resolve_config_level_target(config) == expected


@pytest.mark.parametrize(
    "config",
    [
        SimpleNamespace(advertiser_id=None, offer_id=None, publisher_id=None),
        SimpleNamespace(advertiser_id=11, offer_id=22, publisher_id=None),
        SimpleNamespace(advertiser_id=11, offer_id=None, publisher_id=33),
        SimpleNamespace(advertiser_id=None, offer_id=22, publisher_id=33),
        SimpleNamespace(advertiser_id=0, offer_id=None, publisher_id=None),
        SimpleNamespace(advertiser_id=-1, offer_id=None, publisher_id=None),
        SimpleNamespace(advertiser_id=True, offer_id=None, publisher_id=None),
    ],
)
def test_resolve_config_level_target_rejects_invalid_scope_data(config):
    with pytest.raises(HTTPException):
        resolve_config_level_target(config)
