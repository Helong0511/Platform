"""PTB 22.8 的 getUpdates 请求使用独立 HTTPXRequest，超时必须与长轮询匹配。"""
import ast
from pathlib import Path


def _load_polling_ast():
    path = Path(__file__).resolve().parents[1] / "app/core/telegram/polling_manager.py"
    return ast.parse(path.read_text(encoding="utf-8"))


def _module_constants(tree):
    values = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "POLLING_LONG_POLL_TIMEOUT_SECONDS",
                    "POLLING_GET_UPDATES_READ_TIMEOUT_SECONDS",
                    "POLLING_BOOTSTRAP_RETRIES",
                }:
                    values[target.id] = ast.literal_eval(node.value)
    return values


def test_get_updates_read_timeout_exceeds_long_poll_timeout():
    tree = _load_polling_ast()
    values = _module_constants(tree)
    read_timeout_name = None
    long_poll_timeout_name = None
    bootstrap_retries_name = None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get_updates_read_timeout":
            read_timeout_name = node.args[0].id
        if isinstance(node.func, ast.Attribute) and node.func.attr == "run_polling":
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            long_poll_timeout_name = kwargs["timeout"].id
            bootstrap_retries_name = kwargs["bootstrap_retries"].id

    assert read_timeout_name == "POLLING_GET_UPDATES_READ_TIMEOUT_SECONDS"
    assert values[read_timeout_name] == 65.0
    assert values[long_poll_timeout_name] == 10.0
    assert values[bootstrap_retries_name] == 3
    assert values[read_timeout_name] > values[long_poll_timeout_name]


def test_polling_timeout_constants_are_safe_for_long_polling():
    values = _module_constants(_load_polling_ast())

    assert values["POLLING_LONG_POLL_TIMEOUT_SECONDS"] == 10.0
    assert values["POLLING_GET_UPDATES_READ_TIMEOUT_SECONDS"] > values["POLLING_LONG_POLL_TIMEOUT_SECONDS"]
    assert values["POLLING_BOOTSTRAP_RETRIES"] == 3
