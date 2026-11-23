"""定时任务失败日志和 last_error 不得泄露原始异常详情。"""
import logging

import pytest

from app.scheduler_module.task_utils import log_scheduled_task_failure


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("mysql://svc:password@db.internal:3306/platform SELECT * FROM users"),
        "Bearer super-secret-token from upstream provider",
    ],
)
def test_scheduled_task_failure_redacts_exception_and_extra_values(error, caplog):
    secret = str(error)

    with caplog.at_level(logging.ERROR):
        summary = log_scheduled_task_failure(
            "daily-report",
            error,
            trigger="task_queue",
            extra={"authorization": "Bearer extra-secret", "detail": secret},
        )

    assert secret not in summary
    assert secret not in caplog.text
    assert "extra-secret" not in caplog.text
    assert "任务执行失败，详细错误信息已隐藏" in summary
    assert "error_type=" in caplog.text


def test_recorded_failure_log_does_not_emit_result_message(caplog):
    from app.scheduler_module.task_utils import log_scheduled_task_failure_recorded

    secret = "postgresql://user:password@db.internal/app"
    with caplog.at_level(logging.WARNING):
        log_scheduled_task_failure_recorded(
            "daily-report",
            secret,
            error_count=1,
            success_count=0,
            run_count=1,
        )

    assert secret not in caplog.text
    assert "last_error_present=True" in caplog.text
