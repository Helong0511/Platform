"""全库代码质量筛查（缺失导入、HTTPException 吞没、重复 handler）。"""
from __future__ import annotations

import ast
import os
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

SYMS = [
    "settings",
    "JWTUtils",
    "logger",
    "ErrorCode",
    "get_db",
    "get_app_now_naive",
    "get_client_ip",
    "raise_api_exception",
    "raise_auth_error",
    "ResponseBaseSchema",
    "HTTPException",
]

SKIP_DIRS = {"__pycache__", ".git", "venv", "node_modules"}


def module_defs(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name != "*":
                    names.add(a.asname or a.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def find_missing_symbols(path: Path) -> list[tuple[str, int, str]]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, str(path))
    except SyntaxError:
        return []
    defs = module_defs(tree)
    issues = []
    for sym in SYMS:
        if sym == "logger" and ("getLogger" in text or "logger =" in text):
            if "logger" in defs:
                continue
        if sym not in defs:
            for m in re.finditer(rf"\b{re.escape(sym)}\b", text):
                line = text[: m.start()].count("\n") + 1
                issues.append((str(path.relative_to(ROOT)), line, sym))
    return issues


def _call_raises_api(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Name):
        return node.func.id in ("raise_api_exception", "raise_auth_error")
    if isinstance(node.func, ast.Attribute):
        return node.func.attr in ("raise_api_exception", "raise_auth_error")
    return False


def _try_body_has_raise_api(try_node: ast.Try) -> bool:
    """仅检查 try 主体（不含 except/finally；嵌套 try 只查其 body）。"""

    def walk_stmts(stmts: list[ast.stmt]) -> bool:
        for stmt in stmts:
            if isinstance(stmt, ast.Try):
                if walk_stmts(stmt.body):
                    return True
                continue
            for n in ast.walk(stmt):
                if isinstance(n, ast.Try) and n is not stmt:
                    continue
                if isinstance(n, ast.Call) and _call_raises_api(n):
                    return True
        return False

    return walk_stmts(try_node.body)


def find_swallowed_http(path: Path) -> list[int]:
    text = path.read_text(encoding="utf-8")
    if "raise_api_exception" not in text and "raise_auth_error" not in text:
        return []
    try:
        tree = ast.parse(text, str(path))
    except SyntaxError:
        return []
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not _try_body_has_raise_api(node):
            continue
        has_http_handler = False
        broad_handlers: list[ast.ExceptHandler] = []
        for h in node.handlers:
            if isinstance(h.type, ast.Name) and h.type.id == "HTTPException":
                has_http_handler = True
            elif isinstance(h.type, ast.Name) and h.type.id == "Exception":
                broad_handlers.append(h)
        if broad_handlers and not has_http_handler:
            for h in broad_handlers:
                if h.lineno:
                    lines.append(h.lineno)
    return lines


def find_duplicate_http_handlers(path: Path) -> list[int]:
    text = path.read_text(encoding="utf-8")
    pat = re.compile(
        r"(    except HTTPException:\n        raise\n)(?:    except HTTPException:\n        raise\n)+",
        re.MULTILINE,
    )
    if not pat.search(text):
        return []
    return [m.start() for m in pat.finditer(text)]


def find_bad_import_order(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return text.startswith("from fastapi import HTTPException\n\"\"\"")


def iter_py(base: Path):
    for dp, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(".py"):
                yield Path(dp) / f


def main() -> int:
    missing: list[tuple[str, int, str]] = []
    swallowed: dict[str, list[int]] = defaultdict(list)
    dup_http: list[str] = []
    bad_order: list[str] = []
    syntax_err: list[str] = []

    for path in iter_py(APP):
        rel = str(path.relative_to(ROOT))
        try:
            ast.parse(path.read_text(encoding="utf-8"), rel)
        except SyntaxError as e:
            syntax_err.append(f"{rel}: {e}")
            continue
        missing.extend(find_missing_symbols(path))
        sw = find_swallowed_http(path)
        if sw:
            swallowed[rel] = sw
        if find_duplicate_http_handlers(path):
            dup_http.append(rel)
        if find_bad_import_order(path):
            bad_order.append(rel)

    print("=== 语法错误 ===")
    print(len(syntax_err))
    for x in syntax_err[:20]:
        print(" ", x)

    print("\n=== 疑似缺失符号（需人工确认）===")
    by_file: dict[str, list] = defaultdict(list)
    for f, ln, sym in missing:
        by_file[f].append((ln, sym))
    real_missing = []
    for f, items in sorted(by_file.items()):
        syms = {s for _, s in items}
        if "logger" in syms and len(syms) == 1:
            continue
        real_missing.append((f, items))
    print(f"文件数: {len(real_missing)}")
    for f, items in real_missing[:30]:
        print(f"  {f}: {items[:5]}")

    print("\n=== HTTPException 可能被吞（try 内含 raise_api_exception 但无 except HTTPException）===")
    print(f"文件数: {len(swallowed)}")
    for f, lns in sorted(swallowed.items())[:40]:
        print(f"  {f}: lines {lns[:8]}")

    print("\n=== 重复 except HTTPException ===")
    for f in dup_http:
        print(" ", f)

    print("\n=== import 在 docstring 前 ===")
    for f in bad_order:
        print(" ", f)

    fail = bool(syntax_err or swallowed or dup_http or bad_order)
    if fail:
        print("\n[audit] 发现问题，退出码 1", file=sys.stderr)
    return 1 if fail else 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
