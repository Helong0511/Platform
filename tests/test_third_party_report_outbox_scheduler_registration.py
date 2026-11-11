"""第三方 Report Outbox 调度注册契约测试。"""
from app.scheduler_module.task_config import TASK_CONFIGS
from app.scheduler_module.task_names import (
    ALL_TASK_NAMES,
    THIRD_PARTY_REPORT_OUTBOX_TASK_NAME,
    TASK_NAME_MAP,
)
from app.scheduler_module.task_registry import load_function_by_path
from app.scheduler_module.tasks.third_party_report_tasks import (
    process_third_party_report_outbox_task,
    get_task_result,
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
