


def test_telegram_approval_initialization_failure_uses_callback_bot(monkeypatch):
    from app.core.telegram.callback_handlers import postback_approval as handler
    from app.core.telegram import ptb_runtime

    _patch_telegram_processor(monkeypatch, _FakeTelegramSession(_fake_pending()))
    monkeypatch.setattr(
        ptb_runtime,
        "get_send_bot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bot init failed")),
    )
    delivered = []

    class FallbackBot:
        def answer_callback_query(self, **kwargs):
            delivered.append(kwargs)
            return object()

    monkeypatch.setattr(handler, "_api", lambda _chat_id, _coro: None)
    handler.process_pending_conversion(
        77, "approve", "callback-init-failed", -100123, 8, 555129, FallbackBot()
    )

    assert delivered == [{
        "callback_query_id": "callback-init-failed",
        "text": "处理失败，请稍后重试",
    }]


def test_telegram_approval_session_factory_failure_returns_final_callback(monkeypatch):
    from app.core.telegram.callback_handlers import postback_approval as handler

    db = _FakeTelegramSession(_fake_pending())
    _patch_telegram_processor(monkeypatch, db)
    delivered = []

    class FakeBot:
        def answer_callback_query(self, **kwargs):
            delivered.append(kwargs)
            return object()

    monkeypatch.setattr(
        handler,
        "get_sync_session_factory",
        lambda: (_ for _ in ()).throw(RuntimeError("session factory failed")),
    )
    monkeypatch.setattr(handler, "_api", lambda _chat_id, _coro: None)

    handler.process_pending_conversion(
        77, "approve", "callback-session-init-failed", -100123, 8, 555130, FakeBot()
    )

    assert db.committed is False
    assert delivered == [{
        "callback_query_id": "callback-session-init-failed",
        "text": "处理失败，请稍后重试",
    }]


def test_post_commit_refresh_failure_does_not_report_approval_as_failed(monkeypatch):
    from app.core.telegram.callback_handlers import postback_approval as handler

    db = _FakeTelegramSession(_fake_pending(), fail_refresh=True)
    handler = _patch_telegram_processor(monkeypatch, db)
    delivered = []

    class FakeBot:
        def answer_callback_query(self, **kwargs):
            delivered.append(kwargs)
            return object()

    from app.core.telegram import ptb_runtime
    monkeypatch.setattr(ptb_runtime, "get_send_bot", lambda *_args, **_kwargs: FakeBot())
    monkeypatch.setattr(handler, "_api", lambda _chat_id, _coro: None)

    handler.process_pending_conversion(
        77, "approve", "callback-post-commit-refresh-failed", -100123, 8, 555131
    )

    assert db.committed is True
    assert delivered == [{
        "callback_query_id": "callback-post-commit-refresh-failed",
        "text": "审批已完成，但消息更新失败，请刷新记录状态",
    }]
