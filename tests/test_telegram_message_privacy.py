"""Telegram Bot 不应注册记录普通消息正文的调试型全量处理器。"""
from app.core.telegram import polling_manager


def test_register_handlers_does_not_add_catch_all_message_handler(monkeypatch):
    monkeypatch.setattr(polling_manager, "_handlers_registered", False)

    class FakeApplication:
        def __init__(self):
            self.handlers = []

        def add_handler(self, handler):
            self.handlers.append(handler)

    application = FakeApplication()
    polling_manager.register_handlers(application)

    handler_types = [type(handler).__name__ for handler in application.handlers]
    assert handler_types.count("CommandHandler") == 4
    assert handler_types.count("CallbackQueryHandler") == 3
    assert "MessageHandler" not in handler_types
