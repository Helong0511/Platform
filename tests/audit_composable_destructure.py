"""对比 composable 的 return 与 Vue 页面：模板用了但未解构的字段。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSABLES = ROOT / "frontend" / "src" / "composables"
VIEWS = ROOT / "frontend" / "src"

RETURN_BLOCK = re.compile(
    r"return\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}\s*;?\s*\}",
    re.DOTALL,
)
RETURN_KEY = re.compile(r"^\s*([A-Za-z_][\w]*)\s*(?:,|:)", re.MULTILINE)

USE_IMPORT = re.compile(
    r"import\s*\{[^}]*\b(use[A-Z]\w*)\b[^}]*\}\s*from\s*['\"]([^'\"]+)['\"]"
)
USE_CALL = re.compile(
    r"const\s*\{([^}]+)\}\s*=\s*(use[A-Z]\w*)\("
)

# 模板中常见引用：{{ x }}、:prop="x"、@evt="x"、v-model="x.y"
TEMPLATE_REF = re.compile(
    r"(?:@|:|\{\{|\bv-model=)\s*[\"']?\s*([A-Za-z_][\w]*)"
)


def composable_return_keys(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    keys: set[str] = set()
    # 找最后一个 return { ... }（export function 内）
    for m in RETURN_BLOCK.finditer(text):
        block = m.group(1)
        for line in block.split("\n"):
            line = line.strip().rstrip(",")
            if not line or line.startswith("//"):
                continue
            km = re.match(r"^([A-Za-z_][\w]*)", line)
            if km:
                keys.add(km.group(1))
    return keys


def parse_destructure(block: str) -> set[str]:
    names: set[str] = set()
    for part in block.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            part = part.split(":")[-1].strip()
        names.add(part)
    return names


def resolve_composable_path(import_path: str, vue_path: Path) -> Path | None:
    if import_path.startswith("@/"):
        rel = import_path[2:]
        candidate = ROOT / "frontend" / "src" / f"{rel}.js"
    elif import_path.startswith("."):
        candidate = (vue_path.parent / f"{import_path}.js").resolve()
    else:
        return None
    return candidate if candidate.is_file() else None


def scan_vue(path: Path) -> list[tuple[str, str, set[str]]]:
    text = path.read_text(encoding="utf-8")
    tmpl_m = re.search(r"<template[^>]*>(.*)</template>", text, re.DOTALL)
    script_m = re.search(r"<script[^>]*>(.*)</script>", text, re.DOTALL)
    if not tmpl_m or not script_m:
        return []
    template = tmpl_m.group(1)
    script = script_m.group(1)

    # composable 名 -> 文件路径
    comp_files: dict[str, Path] = {}
    for m in USE_IMPORT.finditer(script):
        hook, imp = m.group(1), m.group(2)
        p = resolve_composable_path(imp, path)
        if p:
            comp_files[hook] = p

    issues: list[tuple[str, str, set[str]]] = []
    for m in USE_CALL.finditer(script):
        hook = m.group(2)
        destructured = parse_destructure(m.group(1))
        comp_path = comp_files.get(hook)
        if not comp_path:
            continue
        returned = composable_return_keys(comp_path)
        if not returned:
            continue
        # 模板里出现的 return 字段
        used_in_template: set[str] = set()
        for ref in TEMPLATE_REF.findall(template):
            if ref in returned:
                used_in_template.add(ref)
        missing = used_in_template - destructured
        if missing:
            issues.append((hook, str(comp_path.relative_to(ROOT)), missing))
    return issues


def main() -> int:
    vue_files = sorted(VIEWS.rglob("*.vue"))
    total = 0
    for vf in vue_files:
        for hook, comp, missing in scan_vue(vf):
            total += 1
            rel = vf.relative_to(ROOT)
            print(f"{rel}")
            print(f"  composable: {hook} ({comp})")
            print(f"  模板使用但未解构: {', '.join(sorted(missing))}\n")
    if total == 0:
        print("未发现 composable 字段「模板用了但未解构」的问题。")
        return 0
    print(f"共 {total} 个文件有问题。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
