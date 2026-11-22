"""Postback GET 参数只能发送一次的回归测试。"""
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock

import pytest

from app.core.postback import forwarder as forwarder_module
from app.core.postback.forwarder import PostbackForwarder


class _FakeSession:
    def add(self, _instance):
        pass

    async def flush(self):
        pass


def _conversion():
    return SimpleNamespace(
        id=101,
        conversion_id="conversion-101",
        platform="test",
        click_id="click-101",
        payout=12.5,
        event_name="install",
        event_value=None,
        ip="203.0.113.10",
        product_id=202,
    )


@pytest.mark.asyncio
async def test_publisher_get_query_parameters_are_not_duplicated(monkeypatch):
    association = {
        "publisher_id": 303,
        "click_id": "click-101",
        "offer_id": 404,
        "url_params": {},
    }
    publisher = SimpleNamespace(
        postback_url="https://downstream.example/callback?source=campaign",
        postback_method="GET",
        postback_success_check=None,
        is_active=True,
        publisher_name="test-publisher",
    )
    monkeypatch.setattr(
        forwarder_module,
        "build_click_association_payload",
        lambda value: dict(value),
    )
    monkeypatch.setattr(
        forwarder_module.CacheManager,
        "get_cached_publisher",
        AsyncMock(return_value=publisher),
    )
    send_request = AsyncMock(return_value=(True, 200, "ok"))
    monkeypatch.setattr(forwarder_module.HttpClient, "send_request", send_request)
    monkeypatch.setattr(
        PostbackForwarder,
        "_send_success_notification",
        AsyncMock(),
    )

    await PostbackForwarder.forward_to_publisher(
        _conversion(), _FakeSession(), click_association=association
    )

    kwargs = send_request.await_args.kwargs
    assert kwargs["params"] is None
    query = parse_qs(urlsplit(kwargs["url"]).query)
    assert query["source"] == ["campaign"]
    assert query["conversion_id"] == ["conversion-101"]
    assert query["click_id"] == ["click-101"]
    assert query["clickid"] == ["click-101"]
    assert query["offer_id"] == ["404"]


@pytest.mark.asyncio
async def test_product_get_query_parameters_are_not_duplicated(monkeypatch):
    association = {
        "click_id": "click-101",
        "offer_id": 404,
        "url_params": {},
    }
    product = SimpleNamespace(
        downstream_postback_url="https://downstream.example/callback?source=product",
        downstream_postback_method="GET",
        downstream_postback_success_check=None,
        is_active=True,
    )
    monkeypatch.setattr(
        forwarder_module,
        "build_click_association_payload",
        lambda value: dict(value),
    )
    monkeypatch.setattr(
        forwarder_module.CacheManager,
        "get_cached_product",
        AsyncMock(return_value=product),
    )
    send_request = AsyncMock(return_value=(True, 200, "ok"))
    monkeypatch.setattr(forwarder_module.HttpClient, "send_request", send_request)

    await PostbackForwarder.forward_to_product(
        _conversion(), _FakeSession(), click_association=association
    )

    kwargs = send_request.await_args.kwargs
    assert kwargs["params"] is None
    query = parse_qs(urlsplit(kwargs["url"]).query)
    assert query["source"] == ["product"]
    assert query["conversion_id"] == ["conversion-101"]
    assert query["click_id"] == ["click-101"]
    assert query["clickid"] == ["click-101"]
    assert query["offer_id"] == ["404"]
