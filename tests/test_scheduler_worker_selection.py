"""Gunicorn API 多 Worker 的调度器归属选择测试。"""

import pytest

from app.core.config import settings


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({"GUNICORN_ROLE": "api", "ENABLE_SCHEDULER": "true", "SCHEDULER_WORKER": "1"}, True),
        ({"GUNICORN_ROLE": "api", "ENABLE_SCHEDULER": "true", "SCHEDULER_WORKER": "0"}, False),
        ({"GUNICORN_ROLE": "api", "ENABLE_SCHEDULER": "false", "SCHEDULER_WORKER": "1"}, False),
        ({"GUNICORN_ROLE": "scheduler", "ENABLE_SCHEDULER": "false", "SCHEDULER_WORKER": "0"}, True),
        ({"GUNICORN_ROLE": "api", "ENABLE_SCHEDULER": "true"}, True),
        ({"GUNICORN_ROLE": "api", "WORKERS": "4"}, False),
    ],
)
def test_scheduler_role_and_worker_marker_precedence(monkeypatch, environment, expected):
    """显式启用不能覆盖 API Worker 的 SCHEDULER_WORKER=0 单实例标记。"""
    for key in (
        "GUNICORN_ROLE",
        "ENABLE_SCHEDULER",
        "SCHEDULER_WORKER",
        "WORKERS",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    assert settings.should_run_scheduler() is expected
