"""HTTPException 不被 except Exception 误吞的回归测试。"""
import ast
from pathlib import Path

from tests.audit_codebase import _try_body_has_raise_api, find_swallowed_http

ROOT = Path(__file__).resolve().parents[1]


def test_short_link_create_has_http_exception_handler():
    path = ROOT / "app" / "services" / "short_link_service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    create_fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "create_short_link"
    )
    outer_try = next(n for n in ast.walk(create_fn) if isinstance(n, ast.Try) and _try_body_has_raise_api(n))
    handler_types = [
        h.type.id
        for h in outer_try.handlers
        if isinstance(h.type, ast.Name)
    ]
    assert "HTTPException" in handler_types
    assert find_swallowed_http(path) == []


def test_cap_service_commit_handlers_not_flagged_as_swallowed():
    """commit 失败仅在 except 中 raise_api_exception，不应误报为吞 HTTPException。"""
    path = ROOT / "app" / "services" / "cpl" / "cap_service.py"
    assert find_swallowed_http(path) == []
