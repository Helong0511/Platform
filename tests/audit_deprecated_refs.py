"""
扫描仓库内对已弃用模块/路径的引用（用于 CI 与本地排查）。
"""
from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
FRONTEND = ROOT / "frontend" / "src"

# 禁止在生产代码中出现的导入（兼容垫片 auto_bot.py 自身除外）
FORBIDDEN_IMPORT_PREFIXES = (
    "app.core.auto_bot",
    "app.core.response",  # 旧 ResponseBase（code=0）
)

# 允许存在但应逐步淘汰的路径片段（仅报告，不失败）
WARN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("asyncio.get_event_loop()", re.compile(r"asyncio\.get_event_loop\s*\(")),
    ("conversion_log_router 注册", re.compile(r"include_router\s*\(\s*conversion_log")),
    ("旧短链路由 short_link_redirect", re.compile(r"from app\.routes\.short_link_redirect import")),
]

SKIP_DIRS = {"__pycache__", ".git", "venv", "node_modules", "dist"}


def iter_py(base: Path):
    for dp, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(".py"):
                yield Path(dp) / f


def iter_frontend_js(base: Path):
    if not base.exists():
        return
    for dp, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            p = Path(dp) / name
            if p.suffix in (".js", ".vue", ".ts", ".tsx"):
                yield p


def check_python_imports(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    if rel == "app/core/auto_bot.py":
        return []
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    try:
        tree = ast.parse(text, rel)
    except SyntaxError:
        return issues
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                for bad in FORBIDDEN_IMPORT_PREFIXES:
                    if mod == bad or mod.startswith(bad + "."):
                        issues.append(f"{rel}:{node.lineno} import {mod}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for bad in FORBIDDEN_IMPORT_PREFIXES:
                    if node.module == bad or node.module.startswith(bad + "."):
                        issues.append(f"{rel}:{node.lineno} from {node.module} import ...")
    for label, pat in WARN_PATTERNS:
        for m in pat.finditer(text):
            line = text[: m.start()].count("\n") + 1
            issues.append(f"{rel}:{line} [warn] {label}")
    return issues


def check_frontend_deprecated(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(ROOT).as_posix()
    issues: list[str] = []
    if "@deprecated" in text or "auto_bot" in text:
        for i, line in enumerate(text.splitlines(), 1):
            if "@deprecated" in line or "auto_bot" in line:
                issues.append(f"{rel}:{i} {line.strip()[:120]}")
    if re.search(r"from\s+['\"].*api/user['\"]", text) and "logout" in text:
        if re.search(r"import\s*\{[^}]*\blogout\b", text):
            issues.append(f"{rel} [warn] 从 api/user 导入 logout（应使用 api/auth）")
    if re.search(r"\bshortLinkFormRules\b", text) and "createShortLinkFormRules" not in text:
        if "export const shortLinkFormRules" not in text:
            issues.append(f"{rel} [warn] 使用已弃用 shortLinkFormRules")
    return issues


def main() -> int:
    forbidden: list[str] = []
    warnings: list[str] = []

    for path in iter_py(APP):
        for issue in check_python_imports(path):
            if "[warn]" in issue:
                warnings.append(issue)
            else:
                forbidden.append(issue)

    for path in iter_py(ROOT / "tests"):
        if path.name == "audit_deprecated_refs.py":
            continue
        for issue in check_python_imports(path):
            if "[warn]" in issue:
                warnings.append(issue)
            else:
                forbidden.append(issue)

    for path in iter_frontend_js(FRONTEND):
        for issue in check_frontend_deprecated(path):
            if "[warn]" in issue:
                warnings.append(issue)
            else:
                forbidden.append(issue)

    print("=== 禁止的弃用导入（应为 0）===")
    print(len(forbidden))
    for x in forbidden[:30]:
        print(" ", x)

    print("\n=== 建议关注的弃用/兼容项 ===")
    print(len(warnings))
    for x in warnings[:40]:
        print(" ", x)

    # 静态：auto_bot 仅自身
    auto_bot_refs = []
    for path in iter_py(ROOT):
        if path.name.endswith(".py") and path != APP / "core" / "auto_bot.py":
            t = path.read_text(encoding="utf-8", errors="replace")
            if "auto_bot" in t:
                auto_bot_refs.append(path.relative_to(ROOT).as_posix())
    print("\n=== 含 auto_bot 字符串的文件（除兼容垫片外应为 0）===")
    print(len(auto_bot_refs))
    for x in auto_bot_refs[:20]:
        print(" ", x)

    fail = bool(forbidden) or bool(auto_bot_refs)
    if fail:
        print("\n[audit_deprecated] 发现问题，退出码 1", file=sys.stderr)
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
