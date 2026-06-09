"""
扫描仓库代码文件，统计缺少模块级文档字符串（docstring/文件头注释）的文件。

用于分批推进「全项目中文注释」时确定优先级；不修改任何源文件。

用法（项目根目录）：
    python tests/comment_coverage_audit.py
    python tests/comment_coverage_audit.py --missing-only
    python tests/comment_coverage_audit.py --dir app/core
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

# 扫描的扩展名
CODE_EXTENSIONS = {".py", ".js", ".vue", ".ts", ".tsx"}

# 排除目录名片段
SKIP_DIR_PARTS = {
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".git",
    "alembic/versions",
}

# Vue/JS 文件头注释：/** ... */ 或 <!-- ... -->
_JS_BLOCK_COMMENT = re.compile(r"^\s*/\*\*[\s\S]*?\*/", re.MULTILINE)
_HTML_COMMENT = re.compile(r"^\s*<!--[\s\S]*?-->", re.MULTILINE)
_PY_TRIPLE = re.compile(r'^\s*("""|\'\'\')[\s\S]*?\1', re.MULTILINE)


def _should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    for part in SKIP_DIR_PARTS:
        if part in rel:
            return True
    return False


def _strip_python_preamble(text: str) -> str:
    """去掉 shebang、encoding cookie 等前导行，便于识别紧随其后的模块 docstring。"""
    lines = text.lstrip("\ufeff").splitlines()
    while lines:
        line = lines[0].strip()
        if not line:
            lines.pop(0)
            continue
        if line.startswith("#!") or re.match(r"^#\s*-\*-", line) or line == "# -*- coding: utf-8 -*-":
            lines.pop(0)
            continue
        break
    return "\n".join(lines).lstrip()


def _has_module_doc(text: str, suffix: str) -> bool:
    stripped = text.lstrip("\ufeff").lstrip()
    if not stripped:
        return True  # 空文件跳过
    if suffix == ".py":
        return bool(_PY_TRIPLE.match(_strip_python_preamble(text)))
    if suffix in (".js", ".ts", ".tsx"):
        return bool(_JS_BLOCK_COMMENT.match(stripped))
    if suffix == ".vue":
        # 优先看 script 前或 template 前的注释
        if _HTML_COMMENT.search(stripped[:800]):
            return True
        script_match = re.search(r"<script[^>]*>", stripped)
        if script_match:
            after = stripped[script_match.end() :]
            return bool(_JS_BLOCK_COMMENT.match(after.lstrip()))
        return bool(_JS_BLOCK_COMMENT.match(stripped))
    return False


def iter_code_files(root: Path, subdir: str | None) -> list[Path]:
    base = root / subdir if subdir else root
    files: list[Path] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in CODE_EXTENSIONS:
            continue
        if _should_skip(path, root):
            continue
        files.append(path)
    return sorted(files)


def main() -> None:
    parser = argparse.ArgumentParser(description="代码注释覆盖率审计")
    parser.add_argument("--dir", default=None, help="仅扫描子目录，如 app/core")
    parser.add_argument("--missing-only", action="store_true", help="只输出缺文件头说明的路径")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    files = iter_code_files(root, args.dir)
    missing: list[Path] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _has_module_doc(text, f.suffix):
            missing.append(f)

    total = len(files)
    covered = total - len(missing)
    print(f"扫描目录: {args.dir or '全项目'}")
    print(f"代码文件: {total}，已有文件头说明: {covered}，缺失: {len(missing)}")
    if args.missing_only or missing:
        print("--- 缺失文件头说明 ---")
        for f in missing:
            print(f.relative_to(root).as_posix())


if __name__ == "__main__":
    main()

# 可作为脚本执行：python tests/comment_coverage_audit.py
