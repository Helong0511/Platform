"""运行时 Telegram 告警不得发送异常正文、上下文或堆栈。"""
from app.core.telegram.runtime_error_notify import build_runtime_error_message


def test_runtime_alert_omits_sensitive_exception_payloads():
    message = build_runtime_error_message(
        error_type="DatabaseError",
        error_message="postgresql://user:password@db.example/private?token=secret",
        location={
            "module": "app.services.example",
            "function": "load_record",
            "line": "42",
            "file": "/srv/private/application.py",
        },
        context={
            "authorization": "Bearer secret-token",
            "request_body": "customer@example.com",
            "client_ip": "203.0.113.9",
        },
        stack_trace="Traceback with password=super-secret",
    )

    # Telegram 消息必须使用真实换行，不能输出字面量反斜杠+n。
    assert "\n服务：" in message
    assert "\\n服务：" not in message
    assert "DatabaseError" in message
    assert "app.services.example" in message
    assert "load_record" in message
    assert "42" in message
    for secret in (
        "postgresql://",
        "password",
        "secret-token",
        "customer@example.com",
        "203.0.113.9",
        "203.0.113.9",
        "Traceback",
        "/srv/private",
    ):
        assert secret not in message
    assert "受访问控制的服务器日志" in message
