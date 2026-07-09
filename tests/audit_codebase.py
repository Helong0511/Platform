#!/usr/bin/env python3
"""
代码库静态审计（CI 门禁）。

检查项：
- app/ 下 Python 源文件可被 compileall 编译
- 关键包与模块可导入（抽样核心入口）
- 禁止明显危险模式（eval/exec 在业务代码中的裸用，排除注释）
"""
from __future__ import annotations

import compileall
import os
import py_compile
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
ERRORS: list[str] = []


def check_compile() -> None:
    """编译 app 包，收集失败文件。"""
    ok = compileall.compile_dir(
        str(APP_DIR),
        quiet=1,
        force=False,
        legacy=False,
    )
    if not ok:
        # 逐文件定位失败点
        for path in APP_DIR.rglob("*.py"):
            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as e:
                ERRORS.append(f"compile: {e}")


def check_core_imports() -> None:
    """抽样导入核心模块，尽早发现 ImportError。

    不导入 app.main（会拉起完整应用与外部依赖）；仅测包结构与核心库。
    """
    sys.path.insert(0, str(ROOT))
    # CI 无真实 DB 时保证 Settings 可初始化
    os.environ.setdefault(
        "SECRET_KEY", "ci-test-secret-key-must-be-at-least-32-chars-long"
    )
    os.environ.setdefault("PRODUCTION_ENV", "development")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("UNIT_TEST", "1")
    os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "ci-test-password-not-for-prod")

    modules = [
        "app.core.config",
        "app.core.cap",
        "app.core.deduction.deduction_manager",
        "app.core.ad_data_metadata",
        "app.schemas.base",
    ]
    for name in modules:
        try:
            __import__(name)
        except Exception as e:
            ERRORS.append(f"import {name}: {type(e).__name__}: {e}")


def check_dangerous_patterns() -> None:
    """扫描业务代码中的危险调用（忽略注释行与已知安全用法）。"""
    skip_parts = {"__pycache__", "examples"}
    for path in APP_DIR.rglob("*.py"):
        if any(part in skip_parts for part in path.parts):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            ERRORS.append(f"read {path}: {e}")
            continue
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            # 仅拦截裸 eval/exec；redis.eval / client.eval 等带属性调用放行
            if re.search(r"(?<![\w.])eval\(", line):
                rel = path.relative_to(ROOT)
                ERRORS.append(f"dangerous {rel}:{i}: bare eval(")
            if re.search(r"(?<![\w.])exec\(", line):
                rel = path.relative_to(ROOT)
                ERRORS.append(f"dangerous {rel}:{i}: bare exec(")


def main() -> int:
    check_compile()
    # 导入依赖较重，CI 已安装 requirements；本地缺依赖时仍报告
    check_core_imports()
    check_dangerous_patterns()
    if ERRORS:
        print("CODEBASE AUDIT FAILED")
        for err in ERRORS:
            print(f"  - {err}")
        return 1
    print("CODEBASE AUDIT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
