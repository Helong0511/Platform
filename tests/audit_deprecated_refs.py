#!/usr/bin/env python3
"""
废弃引用审计（CI 门禁）。

扫描仓库内源码，禁止继续引用已废弃路径/符号。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (模式, 说明) — 命中即失败
DEPRECATED_PATTERNS: list[tuple[str, str]] = [
    ("from app.core.session import", "请使用 app.core.database / 会话相关新模块"),
    ("app.api.v1", "请使用 app.api_v1"),
    ("from app.api import", "旧 api 包已废弃，请使用 app.api_v1"),
    ("TODO_REMOVE_ME", "临时占位标记不得合入"),
]

SCAN_GLOBS = ("*.py", "*.js", "*.vue", "*.mjs", "*.ts")
SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    "dist",
    ".venv",
    "venv",
    "__pycache__",
    ".cache",
    "logs",
    "secrets",
    "keys",
}


def iter_source_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lstrip(".") and f"*{path.suffix}" not in {
            g if g.startswith("*") else f"*{g}" for g in SCAN_GLOBS
        }:
            # 用后缀匹配
            if path.suffix not in {".py", ".js", ".vue", ".mjs", ".ts"}:
                continue
        else:
            if path.suffix not in {".py", ".js", ".vue", ".mjs", ".ts"}:
                continue
        yield path


def main() -> int:
    hits: list[str] = []
    for path in iter_source_files():
        # 跳过本审计脚本自身对模式的声明
        if path.name in {"audit_deprecated_refs.py", "audit_codebase.py"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern, hint in DEPRECATED_PATTERNS:
            if pattern in text:
                rel = path.relative_to(ROOT)
                hits.append(f"{rel}: `{pattern}` — {hint}")

    if hits:
        print("DEPRECATED REFS AUDIT FAILED")
        for h in hits:
            print(f"  - {h}")
        return 1
    print("DEPRECATED REFS AUDIT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
