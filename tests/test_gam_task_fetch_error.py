"""
GAM 定时任务拉数失败 → last_error 容错相关单测。

覆盖：
1. NO_NETWORKS_TO_ACCESS 等鉴权错误的中文摘要
2. 失败账号生成带 fetch_error 的 bundle
3. google_api_task 在部分账号失败时抛错并 set_task_result（供调度器写入 last_error）
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.scheduler_module.gam_api_fetch import (
    _format_account_fetch_failure,
    format_gam_auth_error,
)
from app.scheduler_module.task_names import GAM_API_TASK_NAME
from app.scheduler_module.tasks.gam_task import (
    _collect_fetch_failures,
    google_api_task,
)


def test_format_gam_auth_error_no_networks_to_access():
    """NO_NETWORKS_TO_ACCESS 须转为可读中文，便于 last_error 展示。"""
    exc = Exception(
        "[AuthenticationError.NO_NETWORKS_TO_ACCESS @ ]"
    )
    err = format_gam_auth_error(
        exc,
        account_key="leadwin",
        network_code="23348711678",
        credentials_path=None,
    )
    text = str(err)
    assert "NO_NETWORKS_TO_ACCESS" in text
    assert "leadwin" in text
    assert "23348711678" in text
    assert "服务账号未关联" in text


def test_format_account_fetch_failure_sets_fetch_error():
    """单账号失败须生成 fetch_error bundle，且不依赖其他账号 warnings。"""
    cfg = {
        "account_key": "leadwin",
        "network_code": "23348711678",
        "application_name": "Leadwin",
        "credentials_path": None,
        "start_date": date(2026, 7, 8),
        "end_date": date(2026, 7, 8),
    }
    summary, bundle = _format_account_fetch_failure(
        cfg,
        Exception("[AuthenticationError.NO_NETWORKS_TO_ACCESS @ ]"),
    )
    assert "leadwin" in summary
    assert "NO_NETWORKS_TO_ACCESS" in summary
    assert bundle["fetch_error"]
    assert "NO_NETWORKS_TO_ACCESS" in bundle["fetch_error"]
    assert bundle["reports"] == {}


def test_collect_fetch_failures():
    """从 bundles 收集拉数失败摘要。"""
    bundles = [
        {"account_key": "ok", "network_code": "1", "reports": {}},
        {
            "account_key": "leadwin",
            "network_code": "23348711678",
            "fetch_error": "服务账号未关联任何可访问的 GAM Network（NO_NETWORKS_TO_ACCESS）。",
        },
    ]
    failures = _collect_fetch_failures(bundles)
    assert len(failures) == 1
    assert "leadwin" in failures[0]
    assert "NO_NETWORKS_TO_ACCESS" in failures[0]


@pytest.mark.asyncio
async def test_google_api_task_partial_fetch_failure_sets_last_error_result():
    """
    部分账号拉数失败时：须 set_task_result 含失败原因，并抛 RuntimeError，
    使调度器以 success=False 写入 last_error / error_count。
    """
    ok_bundle = {
        "account_key": "x_browser",
        "network_code": "23347342743",
        "reports": {"country": []},
        "start_date": "2026-07-08",
        "end_date": "2026-07-08",
    }
    fail_bundle = {
        "account_key": "leadwin",
        "network_code": "23348711678",
        "fetch_error": "服务账号未关联任何可访问的 GAM Network（NO_NETWORKS_TO_ACCESS）。",
        "reports": {},
    }

    with (
        patch(
            "app.scheduler_module.tasks.gam_task.gam_scheduler_config_exists",
            return_value=True,
        ),
        patch(
            "app.scheduler_module.tasks.gam_task.resolve_gam_scheduler_accounts",
            return_value=[
                {"key": "x_browser", "report_keys": ["country"]},
                {"key": "leadwin", "report_keys": ["country"]},
            ],
        ),
        patch(
            "app.scheduler_module.tasks.gam_task.resolve_upstream_date_range",
            return_value=("2026-07-08", "2026-07-08"),
        ),
        patch(
            "app.scheduler_module.tasks.gam_task.run_gam_fetch_to_memory",
            return_value=[ok_bundle, fail_bundle],
        ),
        patch(
            "app.scheduler_module.tasks.gam_task.import_gam_account_bundle",
            new_callable=AsyncMock,
            return_value="country: 无数据",
        ) as import_mock,
        patch(
            "app.scheduler_module.tasks.gam_task.set_task_result"
        ) as set_result,
    ):
        with pytest.raises(RuntimeError) as raised:
            await google_api_task()

    message = str(raised.value)
    assert "部分失败" in message
    assert "leadwin" in message
    assert "NO_NETWORKS_TO_ACCESS" in message
    assert "x_browser" in message

    set_result.assert_called()
    stored = set_result.call_args[0][1]
    assert set_result.call_args[0][0] == GAM_API_TASK_NAME
    assert "部分失败" in stored
    assert "NO_NETWORKS_TO_ACCESS" in stored

    # 失败账号不得入库
    import_mock.assert_awaited_once()
    assert import_mock.await_args.args[0]["account_key"] == "x_browser"


@pytest.mark.asyncio
async def test_google_api_task_all_fetch_failure_raises():
    """全部账号拉数失败时，拉数层 RuntimeError 须写入结果并向上抛出。"""
    with (
        patch(
            "app.scheduler_module.tasks.gam_task.gam_scheduler_config_exists",
            return_value=True,
        ),
        patch(
            "app.scheduler_module.tasks.gam_task.resolve_gam_scheduler_accounts",
            return_value=[{"key": "leadwin", "report_keys": ["country"]}],
        ),
        patch(
            "app.scheduler_module.tasks.gam_task.resolve_upstream_date_range",
            return_value=("2026-07-08", "2026-07-08"),
        ),
        patch(
            "app.scheduler_module.tasks.gam_task.run_gam_fetch_to_memory",
            side_effect=RuntimeError(
                "leadwin(23348711678): 服务账号未关联任何可访问的 GAM Network"
                "（NO_NETWORKS_TO_ACCESS）。"
            ),
        ),
        patch(
            "app.scheduler_module.tasks.gam_task.set_task_result"
        ) as set_result,
    ):
        with pytest.raises(RuntimeError) as raised:
            await google_api_task()

    assert "NO_NETWORKS_TO_ACCESS" in str(raised.value)
    stored = set_result.call_args[0][1]
    assert "NO_NETWORKS_TO_ACCESS" in stored
