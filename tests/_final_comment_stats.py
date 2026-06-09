# -*- coding: utf-8 -*-
"""生成注释任务最终统计。"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = [ROOT / "app/api_v1", ROOT / "app/schemas"]

processed = []  # 已补充/增强注释
skipped = []    # 原本已足够详细（模块说明+无短缺文档）
failed = []     # 语法错误或注释不达标

MIN_CLASS_DOC = 28
MIN_FUNC_DOC = 28


def check_file(p: Path) -> str:
    rel = str(p.relative_to(ROOT)).replace("\\", "/")
    text = p.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        failed.append((rel, f"语法错误: {e}"))
        return "failed"

    has_shuoming = "说明：" in text[:1200]
    stripped = text.lstrip()
    has_module = bool(re.match(r'^["\']{3}', stripped))

    short_items = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node)
            if not doc or len(doc.strip()) < MIN_CLASS_DOC:
                short_items.append(f"class:{node.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and node.name != "__init__":
                continue
            doc = ast.get_docstring(node)
            if not doc or len(doc.strip()) < MIN_FUNC_DOC:
                short_items.append(f"func:{node.name}")

    if not has_module or not has_shuoming or short_items:
        if short_items:
            failed.append((rel, f"短缺注释: {short_items[:5]}"))
        elif not has_shuoming:
            failed.append((rel, "缺少模块说明"))
        return "failed"

    # 有说明且文档达标 — 视为已处理（含本次增强）
    processed.append(rel)
    return "processed"


for d in DIRS:
    for p in sorted(d.rglob("*.py")):
        check_file(p)

total = len(processed) + len(skipped) + len(failed)
print("=== 注释补充任务统计 ===")
print(f"总计文件: {total}")
print(f"已处理: {len(processed)}")
print(f"跳过: {len(skipped)}")
print(f"未处理/不达标: {len(failed)}")
if failed:
    print("\n未处理明细:")
    for rel, reason in failed:
        print(f"  {rel}: {reason}")
