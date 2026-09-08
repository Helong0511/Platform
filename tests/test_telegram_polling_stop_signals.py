"""Telegram 轮询在守护线程内必须禁用 stop_signals。"""
import ast
from pathlib import Path


def test_run_polling_disables_stop_signals_in_background_thread():
    """生产 gunicorn/uvloop 下非主线程 add_signal_handler 会 ValueError 秒退。"""
    path = Path(__file__).resolve().parents[1] / "app/core/telegram/polling_manager.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name != "run_polling":
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        assert "stop_signals" in kwargs, "run_polling 必须显式传 stop_signals"
        stop = kwargs["stop_signals"]
        assert isinstance(stop, ast.Constant) and stop.value is None
        found = True
    assert found, "polling_manager.start_polling 中未找到 application.run_polling 调用"
