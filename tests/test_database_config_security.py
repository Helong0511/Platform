"""数据库连接配置必须显式注入，禁止源码默认凭据回退。"""

import pytest

from app.core.config import Settings


def test_database_url_is_required_when_environment_value_is_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)

    with pytest.raises(ValueError, match="必须显式设置 DATABASE_URL"):
        Settings.validate_database_uri(None)


def test_database_url_accepts_explicit_environment_value(monkeypatch):
    expected = "mysql+aiomysql://runtime:secret@127.0.0.1:3306/platform?charset=utf8mb4"
    monkeypatch.setenv("DATABASE_URL", expected)

    assert Settings.validate_database_uri(None) == expected


def test_database_url_rejects_blank_environment_value(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "   ")
    monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)

    with pytest.raises(ValueError, match="必须显式设置 DATABASE_URL"):
        Settings.validate_database_uri(None)
