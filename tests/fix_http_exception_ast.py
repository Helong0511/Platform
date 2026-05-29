"""
在 try 体内含 raise_api_exception/raise_auth_error、且仅有 except Exception 时，
于 Exception 处理器前插入 `except HTTPException: raise`。
仅扫描 try 主体，不扫描 except/finally（避免误改 commit 回滚类代码）。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "app" / "services",
    ROOT / "app" / "api_v1",
]

RAISE_NAMES = frozenset({"raise_api_exception", "raise_auth_error"})


def _call_raises_api(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Name):
        return node.func.id in RAISE_NAMES
    if isinstance(node.func, ast.Attribute):
        return node.func.attr in RAISE_NAMES
    return False


def _try_body_has_raise(try_node: ast.Try) -> bool:
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


def _needs_fix(tree: ast.AST) -> list[tuple[int, int]]:
    """返回 (except_exception_lineno, indent_spaces) 待插入位置。"""
    fixes: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not _try_body_has_raise(node):
            continue
        has_http = any(
            isinstance(h.type, ast.Name) and h.type.id == "HTTPException"
            for h in node.handlers
        )
        if has_http:
            continue
        for h in node.handlers:
            if isinstance(h.type, ast.Name) and h.type.id == "Exception" and h.lineno:
                # 从源码行推断缩进（except 行 leading spaces）
                fixes.append((h.lineno, 0))
    return fixes


def _line_indent(lines: list[str], lineno: int) -> int:
    line = lines[lineno - 1]
    return len(line) - len(line.lstrip())


def fix_file(path: Path, dry_run: bool = False) -> int:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, str(path))
    except SyntaxError:
        return 0

    raw_fixes = _needs_fix(tree)
    if not raw_fixes:
        return 0

    lines = text.splitlines(keepends=True)
    # 自下而上插入，避免行号偏移
    insertions: list[tuple[int, str]] = []
    for lineno, _ in raw_fixes:
        indent = _line_indent(lines, lineno)
        pad = " " * indent
        block = f"{pad}except HTTPException:\n{pad}    raise\n"
        insertions.append((lineno - 1, block))

    if not insertions:
        return 0

    # 去重：同一行只插一次
    seen: set[int] = set()
    unique: list[tuple[int, str]] = []
    for idx, block in sorted(insertions, key=lambda x: -x[0]):
        if idx in seen:
            continue
        seen.add(idx)
        unique.append((idx, block))

    new_lines = list(lines)
    for idx, block in unique:
        new_lines.insert(idx, block)

    new_text = "".join(new_lines)
    if "HTTPException" not in text and "HTTPException" in new_text:
        # 在首个 fastapi 导入后追加，否则新建导入
        if "from fastapi import" in new_text:
            import re

            def add_http(m: re.Match[str]) -> str:
                inner = m.group(1)
                if "HTTPException" in inner:
                    return m.group(0)
                parts = [p.strip() for p in inner.split(",")]
                parts.append("HTTPException")
                return f"from fastapi import {', '.join(parts)}"

            new_text = re.sub(
                r"from fastapi import ([^\n]+)",
                add_http,
                new_text,
                count=1,
            )
        elif "from app.core.exceptions import" in new_text:
            new_text = new_text.replace(
                "from app.core.exceptions import",
                "from fastapi import HTTPException\nfrom app.core.exceptions import",
                1,
            )
        else:
            # 模块 docstring 之后插入
            tree2 = ast.parse(new_text, str(path))
            insert_at = 0
            if (
                tree2.body
                and isinstance(tree2.body[0], ast.Expr)
                and isinstance(tree2.body[0].value, ast.Constant)
                and isinstance(tree2.body[0].value.value, str)
            ):
                insert_at = tree2.body[0].end_lineno or 1
            line_list = new_text.splitlines(keepends=True)
            line_list.insert(insert_at, "from fastapi import HTTPException\n")
            new_text = "".join(line_list)

    if dry_run:
        print(f"would fix: {path.relative_to(ROOT)} ({len(unique)} inserts)")
        return len(unique)

    path.write_text(new_text, encoding="utf-8")
    print(f"fixed: {path.relative_to(ROOT)} ({len(unique)} inserts)")
    return len(unique)


def main() -> None:
    dry = "--dry-run" in sys.argv
    total = 0
    for base in TARGETS:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            total += fix_file(path, dry_run=dry)
    print(f"total inserts: {total}")


if __name__ == "__main__":
    main()
