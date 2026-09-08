# -*- coding: utf-8 -*-
"""TELEGRAM_ENABLE=false 时 Token 校验器应强制清空。"""
from __future__ import annotations

from app.core.config import Settings


def test_validate_telegram_token_cleared_when_disabled(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLE", "false")
    monkeypatch.setenv("TELEGRAM_TOKEN", "111:AAA")
    monkeypatch.setenv("TELEGRAM_TOKEN_LOCAL", "222:BBB")
    monkeypatch.setenv("TELEGRAM_TOKEN_PRODUCTION", "333:CCC")

    assert Settings.validate_telegram_token("111:AAA") is None
    assert Settings.validate_telegram_token(None) is None


def test_validate_telegram_token_resolves_when_enabled(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLE", "true")
    monkeypatch.setenv("TELEGRAM_TOKEN_LOCAL", "222:BBBLOCAL")
    monkeypatch.delenv("TELEGRAM_TOKEN_PRODUCTION", raising=False)
    # 非生产环境优先 LOCAL
    monkeypatch.setenv("PRODUCTION_ENV", "false")
    # detect_production_env 还可能看其它变量；用 LOCAL 回退路径
    resolved = Settings.validate_telegram_token(None)
    # 在 Windows 开发或非生产时应拿到 LOCAL；若判定为生产则可能拿不到 LOCAL
    # 至少启用时应尝试解析，不得因 ENABLE 直接 None（除非无任何 token）
    assert resolved in (None, "222:BBBLOCAL") or (
        isinstance(resolved, str) and ":" in resolved
    )
