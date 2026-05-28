"""点击记录 Facebook 补报参数构建测试。"""
from types import SimpleNamespace

import pytest

from app.services.click_service import ClickService


def _build_click(**kwargs):
    base = {
        "click_id": "clk_001",
        "ip": "1.1.1.1",
        "user_agent": "ua-test",
        "click_time": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _build_conversion(**kwargs):
    base = {"id": 1001, "payout": 9.99}
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_build_payload_prefers_fbclid_as_adsid():
    click = _build_click(click_id="clk_fallback")
    conversion = _build_conversion(id=777, payout=12.5)
    payload = ClickService._build_facebook_report_payload(
        click=click,
        conversion=conversion,
        url_params={"fbclid": "fb_123", "email": "a@b.com", "phone": "123"},
        facebook_pixel_id="p1",
        facebook_access_token="t1",
        facebook_api_version="v23.0",
    )
    assert payload["adsid"] == "fb_123"
    assert payload["conversion_id"] == "777"
    assert payload["amount"] == 12.5
    assert payload["event"] == "Purchase"


def test_build_payload_fallback_click_id_when_no_fbclid():
    click = _build_click(click_id="clk_fallback")
    conversion = _build_conversion()
    payload = ClickService._build_facebook_report_payload(
        click=click,
        conversion=conversion,
        url_params={},
        facebook_pixel_id="p1",
        facebook_access_token="t1",
        facebook_api_version="v23.0",
    )
    assert payload["adsid"] == "clk_fallback"


def test_build_payload_requires_positive_amount():
    click = _build_click()
    conversion = _build_conversion(payout=0)
    with pytest.raises(Exception):
        ClickService._build_facebook_report_payload(
            click=click,
            conversion=conversion,
            url_params={"fbclid": "fb_1"},
            facebook_pixel_id="p1",
            facebook_access_token="t1",
            facebook_api_version="v23.0",
        )
