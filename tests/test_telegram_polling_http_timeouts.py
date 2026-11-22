"""PTB 22.8 的 getUpdates 请求使用独立 HTTPXRequest，超时必须与长轮询匹配。"""
import ast
from pathlib import Path


def _load_polling_ast():
    path = Path(__file__).resolve().parents[1] / "app/core/telegram/polling_manager.py"
    return ast.parse(path.read_text(encoding="utf-8"))


def test_get_updates_read_timeout_exceeds_long_poll_timeout():
    tree = _load_polling_ast()
    read_timeout_name = None
    long_poll_timeout = None
    values = {}
    bootstrap_retries = None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get_updates_read_timeout":
            read_timeout_name = node.args[0].id
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "POLLING_LONG_POLL_TIMEOUT_SECONDS",
                    "POLLING_GET_UPDATES_READ_TIMEOUT_SECONDS",
                    "POLLING_BOOTSTRAP_RETRIES",
                }:
                    values[target.id] = ast.literal_eval(node.value)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "run_polling":
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            long_poll_timeout = kwargs["timeout"].id
            bootstrap_retries = kwargs["bootstrap_retries"].id

    assert read_timeout_name == "POLLING_GET_UPDATES_READ_TIMEOUT_SECONDS"
    assert values[read_timeout_name] == 65.0
    assert values[long_poll_timeout] == 10.0
    assert values[bootstrap_retries] == 3
    assert long_poll_timeout == "POLLING_LONG_POLL_TIMEOUT_SECONDS"
    assert bootstrap_retries == "POLLING_BOOTSTRAP_RETRIES"


def test_polling_timeout_constants_are_safe_for_long_polling():
    tree = _load_polling_ast()
    values = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id in {
                        "POLLING_LONG_POLL_TIMEOUT_SECONDS",
                        "POLLING_GET_UPDATES_READ_TIMEOUT_SECONDS",
                        "POLLING_BOOTSTRAP_RETRIES",
                    }:
                        values[target.id] = ast.literal_eval(node.value)

    assert values["POLLING_LONG_POLL_TIMEOUT_SECONDS"] == 10.0
    assert values["POLLING_GET_UPDATES_READ_TIMEOUT_SECONDS"] > values["POLLING_LONG_POLL_TIMEOUT_SECONDS"]
    assert values["POLLING_BOOTSTRAP_RETRIES"] == 3
