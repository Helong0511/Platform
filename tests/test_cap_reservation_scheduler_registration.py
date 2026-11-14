"""Cap Reservation recovery scheduler registration contract."""
from app.scheduler_module.task_config import TASK_CONFIGS
from app.scheduler_module.task_names import (
    ALL_TASK_NAMES,
    CAP_RESERVATION_RECOVERY_TASK_NAME,
    TASK_NAME_MAP,
)
from app.scheduler_module.task_registry import load_function_by_path
from app.scheduler_module.tasks.cap_reservation_recovery import (
    cap_reservation_recovery_task,
    get_task_result,
)


def test_cap_reservation_recovery_task_is_registered_with_scheduler():
    config = TASK_CONFIGS[CAP_RESERVATION_RECOVERY_TASK_NAME]

    assert CAP_RESERVATION_RECOVERY_TASK_NAME in ALL_TASK_NAMES
    assert TASK_NAME_MAP["cap_reservation_recovery"] == CAP_RESERVATION_RECOVERY_TASK_NAME
    assert config["task_name"] == CAP_RESERVATION_RECOVERY_TASK_NAME
    assert config["cron_expression"] == "* * * * *"

    task = load_function_by_path(
        f"{config['task_module']}.{config['task_function']}"
    )
    assert task is cap_reservation_recovery_task

    getter = load_function_by_path(
        f"{config['result_getter_module']}.{config['result_getter_function']}"
    )
    assert getter is get_task_result
