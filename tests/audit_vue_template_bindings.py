"""扫描 Vue SFC：模板中 @事件 绑定的标识符是否在 script 中可见。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "src"

# @click="foo" / @keyup.enter="fetchLogs" / @change="handleSearch"
EVENT_BINDING = re.compile(
    r"@[\w.-]+=\"(?:\(\)\s*=>\s*)?([A-Za-z_][\w]*)\""
)
# const { a, b } = useXxx() 或 const { a, b } = useXxx(auth)
DESTRUCTURE = re.compile(
    r"const\s*\{([^}]+)\}\s*=\s*use[A-Z]\w*\("
)
# script 内局部定义
LOCAL_DEF = re.compile(
    r"(?:const|let|function)\s+([A-Za-z_][\w]*)"
)
# import { a, b } from
IMPORT_NAMED = re.compile(
    r"import\s*\{([^}]+)\}\s*from"
)

BUILTIN = {
    "emit", "true", "false", "null", "undefined",
    "console", "window", "document", "event",
}


def parse_names(block: str) -> set[str]:
    names: set[str] = set()
    for m in DESTRUCTURE.finditer(block):
        for part in m.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            # alias: foo: bar
            if ":" in part:
                part = part.split(":")[-1].strip()
            names.add(part)
    for m in IMPORT_NAMED.finditer(block):
        for part in m.group(1).split(","):
            part = part.strip()
            if part.startswith("type "):
                continue
            if " as " in part:
                part = part.split(" as ")[-1].strip()
            names.add(part)
    for m in LOCAL_DEF.finditer(block):
        names.add(m.group(1))
    return names


def scan_vue(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    tmpl_m = re.search(r"<template[^>]*>(.*)</template>", text, re.DOTALL)
    script_m = re.search(r"<script[^>]*>(.*)</script>", text, re.DOTALL)
    if not tmpl_m or not script_m:
        return []
    template = tmpl_m.group(1)
    script = script_m.group(1)
    scope = parse_names(script) | BUILTIN
    issues: list[tuple[str, str]] = []
    for m in EVENT_BINDING.finditer(template):
        handler = m.group(1)
        if handler not in scope:
            issues.append((handler, m.group(0)))
    return issues


def main() -> int:
    vue_files = sorted(ROOT.rglob("*.vue"))
    all_issues: list[tuple[Path, str, str]] = []
    for vf in vue_files:
        for handler, binding in scan_vue(vf):
            all_issues.append((vf.relative_to(ROOT.parent.parent), handler, binding))

    if not all_issues:
        print("未发现模板事件绑定未定义的问题。")
        return 0

    print(f"发现 {len(all_issues)} 处可疑绑定：\n")
    for path, handler, binding in all_issues:
        print(f"  {path}")
        print(f"    未定义: {handler}  ({binding})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
