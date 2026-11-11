"""第三方 Report Outbox 调度注册契约测试。"""
from app.scheduler_module.task_config import TASK_CONFIGS
from app.scheduler_module.task_names import (
    ALL_TASK_NAMES,
    THIRD_PARTY_REPORT_OUTBOX_TASK_NAME,
    THIRD_PARTY_REPORT_PII_RETENTION_TASK_NAME,
    TASK_NAME_MAP,
)
from app.scheduler_module.task_registry import load_function_by_path
from app.scheduler_module.tasks.third_party_report_tasks import (
    process_third_party_report_outbox_task,
    get_task_result,
    scrub_third_party_report_pii_task,
)


def test_third_party_report_outbox_task_is_registered():
    config = TASK_CONFIGS[THIRD_PARTY_REPORT_OUTBOX_TASK_NAME]

    assert THIRD_PARTY_REPORT_OUTBOX_TASK_NAME in ALL_TASK_NAMES
    assert (
        TASK_NAME_MAP["third_party_report_tasks"]
        == THIRD_PARTY_REPORT_OUTBOX_TASK_NAME
    )
    assert config["task_name"] == THIRD_PARTY_REPORT_OUTBOX_TASK_NAME
    assert config["cron_expression"] == "* * * * *"

    task = load_function_by_path(
        f"{config['task_module']}.{config['task_function']}"
    )
    assert task is process_third_party_report_outbox_task

    getter = load_function_by_path(
        f"{config['result_getter_module']}.{config['result_getter_function']}"
    )
    assert getter is get_task_result


def test_third_party_report_pii_retention_task_is_registered():
    config = TASK_CONFIGS[THIRD_PARTY_REPORT_PII_RETENTION_TASK_NAME]

    assert THIRD_PARTY_REPORT_PII_RETENTION_TASK_NAME in ALL_TASK_NAMES
    assert config["task_name"] == THIRD_PARTY_REPORT_PII_RETENTION_TASK_NAME
    assert config["cron_expression"] == "15 3 * * *"
    task = load_function_by_path(
        f"{config['task_module']}.{config['task_function']}"
    )
    assert task is scrub_third_party_report_pii_task


import logging
import pytest


@pytest.mark.asyncio
async def test_outbox_scheduler_failure_does_not_persist_exception_text(monkeypatch, caplog):
    from app.scheduler_module.tasks import third_party_report_tasks as tasks

    captured = {}

    async def fail(**kwargs):
        raise RuntimeError("buyer@example.invalid 203.0.113.10 secret-payload")

    monkeypatch.setattr(tasks, "process_postback_report_outbox", fail)
    monkeypatch.setattr(
        tasks,
        "set_task_result",
        lambda name, message: captured.update(name=name, message=message),
    )

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
        await tasks.process_third_party_report_outbox_task()

    assert captured["name"] == THIRD_PARTY_REPORT_OUTBOX_TASK_NAME
    assert captured["message"] == "执行失败：RuntimeError"
    assert "buyer@example.invalid" not in caplog.text
    assert "203.0.113.10" not in caplog.text
    assert "secret-payload" not in caplog.text


@pytest.mark.asyncio
async def test_pii_retention_scheduler_failure_does_not_persist_exception_text(
    monkeypatch, caplog
):
    from app.scheduler_module.tasks import third_party_report_tasks as tasks
    from app.services import third_party_report_pii_retention as retention

    captured = {}

    async def fail(**kwargs):
        raise RuntimeError("buyer@example.invalid 203.0.113.10 secret-payload")

    monkeypatch.setattr(retention, "scrub_expired_third_party_report_pii", fail)
    monkeypatch.setattr(
        tasks,
        "set_task_result",
        lambda name, message: captured.update(name=name, message=message),
    )

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
        await tasks.scrub_third_party_report_pii_task()

    assert captured["name"] == THIRD_PARTY_REPORT_PII_RETENTION_TASK_NAME
    assert captured["message"] == "执行失败：RuntimeError"
    assert "buyer@example.invalid" not in caplog.text
    assert "203.0.113.10" not in caplog.text
    assert "secret-payload" not in caplog.text


@pytest.mark.asyncio
async def test_pii_retention_scheduler_runs_one_bounded_combined_sweep(monkeypatch):
    from app.scheduler_module.tasks import third_party_report_tasks as tasks
    from app.services import third_party_report_pii_retention as retention

    calls = []

    async def scrub_reports(**kwargs):
        calls.append(("combined", kwargs["batch_size"]))
        return {
            "enabled": True,
            "selected": 5,
            "scrubbed": 5,
            "third_party_report_logs_scrubbed": 2,
            "postback_forward_logs_scrubbed": 3,
            "retention_days": 90,
        }

    async def unexpected_second_sweep(**kwargs):
        raise AssertionError("综合清理已覆盖下游转发日志，不应重复执行第二次扫描")

    monkeypatch.setattr(retention, "scrub_expired_third_party_report_pii", scrub_reports)
    monkeypatch.setattr(retention, "scrub_expired_postback_forward_log_pii", unexpected_second_sweep)
    monkeypatch.setattr(tasks, "set_task_result", lambda *args: None)

    result = await tasks.scrub_third_party_report_pii_task()

    assert calls == [("combined", 200)]
    assert result["scrubbed"] == 5
    assert result["postback_forward_logs_scrubbed"] == 3


@pytest.mark.asyncio
async def test_pii_retention_scheduler_handles_disabled_policy_without_key_error(monkeypatch):
    from app.scheduler_module.tasks import third_party_report_tasks as tasks
    from app.services import third_party_report_pii_retention as retention

    captured = {}

    async def disabled(**kwargs):
        assert kwargs["batch_size"] == 200
        return {
            "enabled": False,
            "retention_days": 0,
            "selected": 0,
            "scrubbed": 0,
            "third_party_report_logs_scrubbed": 0,
            "postback_forward_logs_scrubbed": 0,
        }

    monkeypatch.setattr(retention, "scrub_expired_third_party_report_pii", disabled)
    monkeypatch.setattr(
        tasks,
        "set_task_result",
        lambda name, message: captured.update(name=name, message=message),
    )

    result = await tasks.scrub_third_party_report_pii_task()

    assert result["enabled"] is False
    assert result["third_party_report_logs_scrubbed"] == 0
    assert result["postback_forward_logs_scrubbed"] == 0
    assert captured["name"] == THIRD_PARTY_REPORT_PII_RETENTION_TASK_NAME
    assert "enabled=False" in captured["message"]
