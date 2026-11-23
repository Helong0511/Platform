"""Telegram polling 启动必须保留停机期间尚未处理的 Updates。"""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.core.telegram import polling_manager as manager


def test_post_init_does_not_drop_pending_updates():
    calls = []

    class FakeBot:
        async def delete_webhook(self, **kwargs):
            calls.append(("delete_webhook", kwargs))

        async def set_my_commands(self, commands):
            calls.append(("set_my_commands", commands))

    asyncio.run(manager._post_init(SimpleNamespace(bot=FakeBot())))

    assert calls[0] == ("delete_webhook", {"drop_pending_updates": False})
    assert calls[1][0] == "set_my_commands"


def test_run_polling_does_not_drop_pending_updates():
    path = Path(manager.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run_polling"
    ]

    assert len(calls) == 1
    kwargs = {item.arg: item.value for item in calls[0].keywords if item.arg}
    assert isinstance(kwargs.get("drop_pending_updates"), ast.Constant)
    assert kwargs["drop_pending_updates"].value is False
