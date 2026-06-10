"""运行平台环境推断单元测试"""
import os

import pytest

from app.core.config import detect_production_env, is_production_env_name


@pytest.mark.parametrize(
    "system,expected",
    [
        ("Windows", "development"),
        ("Linux", "production"),
        ("Darwin", "development"),
    ],
)
def test_detect_production_env_by_platform(monkeypatch, system, expected):
    monkeypatch.delenv("UNIT_TEST", raising=False)
    monkeypatch.setenv("PRODUCTION_ENV", "production")
    monkeypatch.setattr("app.core.config.platform.system", lambda: system)
    assert detect_production_env() == expected


def test_detect_production_env_unit_test_override(monkeypatch):
    monkeypatch.setenv("UNIT_TEST", "1")
    monkeypatch.setenv("PRODUCTION_ENV", "development")
    monkeypatch.setattr("app.core.config.platform.system", lambda: "Linux")
    assert detect_production_env() == "development"


def test_is_production_env_name():
    assert is_production_env_name("production")
    assert is_production_env_name("prod")
    assert not is_production_env_name("development")
