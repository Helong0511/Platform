"""GAM report_keys / product_whitelist 类型校验与 locale 补丁测试。"""
from __future__ import annotations

import locale
import sys
from unittest.mock import patch

import pytest

from app.scheduler_module.gam_api_fetch import (
    _coerce_report_keys_input,
    _ensure_utf8_environment,
    _normalize_account_report_keys,
    _normalize_gam_account,
)
from app.scheduler_module.gam_scheduler_config import (
    normalize_product_whitelist,
    normalize_report_keys,
)


def test_report_keys_int_raises_clear_value_error() -> None:
    with pytest.raises(ValueError, match="不能是数字"):
        _coerce_report_keys_input(23347342743)
    with pytest.raises(ValueError, match="不能是数字"):
        normalize_report_keys(23348711678)


def test_report_keys_string_and_list_normalized() -> None:
    assert normalize_report_keys("country, ad_unit") == ["country", "ad_unit"]
    assert _normalize_account_report_keys(["country"]) == ["country"]


def test_product_whitelist_int_raises_clear_value_error() -> None:
    with pytest.raises(ValueError, match="不能是数字"):
        normalize_product_whitelist(123)


def test_normalize_gam_account_rejects_int_report_keys() -> None:
    with pytest.raises(ValueError, match="不能是数字"):
        _normalize_gam_account(
            {
                "key": "x_browser",
                "credentials_json": "secrets/gam-23347342743.json",
                "report_keys": 23347342743,
            },
            index=0,
        )


def test_getdefaultlocale_patch_skipped_on_linux() -> None:
    """Linux 上不得替换 getdefaultlocale，避免把 LC_ALL 整数误传给 envvars。"""
    original = locale.getdefaultlocale
    if hasattr(locale, "_gam_utf8_patched"):
        delattr(locale, "_gam_utf8_patched")

    with patch.object(sys, "platform", "linux"):
        _ensure_utf8_environment()
        assert locale.getdefaultlocale is original

    # 恢复 Windows 开发机上的模块级副作用
    if hasattr(locale, "_gam_utf8_patched"):
        delattr(locale, "_gam_utf8_patched")
    _ensure_utf8_environment()


def test_gam_cache_dir_defaults_to_project_local() -> None:
    from app.scheduler_module.gam_api_fetch import DEFAULT_GAM_CACHE_DIR, _resolve_gam_cache_dir

    assert _resolve_gam_cache_dir() == DEFAULT_GAM_CACHE_DIR
    assert DEFAULT_GAM_CACHE_DIR.name == "gam"
    assert DEFAULT_GAM_CACHE_DIR.parent.name == ".cache"
