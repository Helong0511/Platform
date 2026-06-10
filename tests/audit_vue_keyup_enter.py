"""校验：模板 @keyup.enter 绑定的 handler 在 script 中已定义。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "src"

KEYUP_ENTER = re.compile(r'@keyup\.enter="(?:\(\)\s*=>\s*)?([A-Za-z_][\w]*)"')
LOCAL_DEF = re.compile(r"(?:const|let|function)\s+([A-Za-z_][\w]*)")
DESTRUCTURE = re.compile(r"const\s*\{([^}]+)\}\s*=")
IMPORT_NAMED = re.compile(r"import\s*\{([^}]+)\}\s*from")


def script_scope(script: str) -> set[str]:
    names: set[str] = set()
    for m in LOCAL_DEF.finditer(script):
        names.add(m.group(1))
    for m in DESTRUCTURE.finditer(script):
        for part in m.group(1).split(","):
            part = part.strip()
            if ":" in part:
                part = part.split(":")[-1].strip()
            if part:
                names.add(part)
    for m in IMPORT_NAMED.finditer(script):
        for part in m.group(1).split(","):
            part = part.strip()
            if " as " in part:
                part = part.split(" as ")[-1].strip()
            if part and not part.startswith("type "):
                names.add(part)
    return names


def main() -> int:
    issues: list[str] = []
    for vf in sorted(ROOT.rglob("*.vue")):
        text = vf.read_text(encoding="utf-8")
        tmpl = re.search(r"<template[^>]*>(.*)</template>", text, re.DOTALL)
        script = re.search(r"<script[^>]*>(.*)</script>", text, re.DOTALL)
        if not tmpl or not script:
            continue
        scope = script_scope(script.group(1))
        for m in KEYUP_ENTER.finditer(tmpl.group(1)):
            handler = m.group(1)
            if handler not in scope:
                rel = vf.relative_to(ROOT.parent.parent)
                issues.append(f"{rel}: @keyup.enter=\"{handler}\" 未在 script 中定义")

    if not issues:
        print("所有 @keyup.enter 绑定的 handler 均已定义。")
        return 0
    print("\n".join(issues))
    return 1


if __name__ == "__main__":
    sys.exit(main())
