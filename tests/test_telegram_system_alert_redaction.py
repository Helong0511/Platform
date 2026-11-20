"""系统告警进入 Telegram 或通知历史前必须移除异常正文和敏感路径。"""
from app.core.telegram_utils import build_alert_message


def test_system_alert_message_omits_description_exception_and_absolute_file_path():
    secret = "password=private-secret https://api.telegram.org/botTOPSECRET/send"
    message = build_alert_message(
        alert_type="database_error",
        description=f"DB connection failed: {secret}",
        location={
            "module": "app.services.worker",
            "function": "run_task",
            "line": "128",
            "file": "/srv/platform/.env?token=TOPSECRET",
        },
        error=RuntimeError(secret),
    )

    assert "system_alert" in message
    assert "RuntimeError" in message
    assert "app.services.worker" in message
    assert "run_task" in message
    assert "128" in message
    assert "private-secret" not in message
    assert "TOPSECRET" not in message
    assert "api.telegram.org" not in message
    assert "/srv/platform" not in message
    assert "DB connection failed" not in message
