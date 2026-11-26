"""Outbox API 版本快照配置回退测试。"""
import pytest

from app.core.config import settings
from app.services.third_party_report_outbox import _normalize_outbox_api_version


@pytest.mark.parametrize(
    ("resolved_version", "configured_version", "expected"),
    [
        ("v22.0", "v23.0", "v22.0"),
        ("   ", "v24.0", "v24.0"),
        (None, "v24.0", "v24.0"),
        ("", "   ", "v23.0"),
        (None, None, "v23.0"),
    ],
)
def test_outbox_api_version_falls_back_from_blank_values(
    monkeypatch, resolved_version, configured_version, expected
):
    monkeypatch.setattr(settings, "FACEBOOK_API_VERSION", configured_version)
    assert _normalize_outbox_api_version(resolved_version) == expected


def test_outbox_api_version_rejects_oversized_value(monkeypatch):
    monkeypatch.setattr(settings, "FACEBOOK_API_VERSION", "v23.0")
    assert _normalize_outbox_api_version("v" + "1" * 20) is None
