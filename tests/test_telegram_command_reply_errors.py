"""Telegram 命令回复失败日志与 /help 文案。"""
import logging

from app.core.telegram.command_handlers._reply_errors import log_command_reply_failure
from app.core.telegram.command_handlers import help_command


def test_log_command_reply_failure_blocked(caplog):
    with caplog.at_level(logging.ERROR):
        log_command_reply_failure(
            "start",
            5312177749,
            Exception("Forbidden: bot was blocked by the user"),
        )
    assert "用户已拉黑该 Bot" in caplog.text
    assert "5312177749" in caplog.text


def test_help_text_uses_html_not_markdown_stars():
    """防止再出现 ** 导致 Telegram Markdown 解析失败。"""
    import inspect

    src = inspect.getsource(help_command.cmd_help)
    assert 'parse_mode="HTML"' in src
    assert "**" not in src
