#!/usr/bin/env python3
"""
预发双轨验证清单（USE_TRACKING_TOKEN=true + PERSIST_CLICKS_TO_DB=true）

双轨含义：
  - click_id 为追踪令牌（Postback 可无 clicks 行也能归因）
  - 同时写入 clicks 表（队列批量落库），便于报表/对账/回填

用法（在项目根目录）：
  python tests/dual_track_prerelease_checklist.py           # 打印人工步骤
  python tests/dual_track_prerelease_checklist.py --env     # 校验 .env 关键项（预发机）
  python tests/dual_track_prerelease_checklist.py --auto    # 跑自动化 pytest 门控
  python tests/dual_track_prerelease_checklist.py --all     # --env + --auto + 打印清单
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# 人工验证清单（预发环境按顺序勾选）
# ---------------------------------------------------------------------------
MANUAL_CHECKLIST: list[dict[str, Any]] = [
    {
        "phase": "A. 配置与启动",
        "items": [
            {
                "id": "A1",
                "step": "确认 .env：USE_TRACKING_TOKEN=true、PERSIST_CLICKS_TO_DB=true、AD_TRACKING_MASTER_KEY_HEX 已设置（64 位 hex）",
                "verify": "python tests/dual_track_prerelease_checklist.py --env",
            },
            {
                "id": "A2",
                "step": "重启后端，在 logs 中搜索「点击落库策略」",
                "verify": "日志应含：强制写库 (PERSIST_CLICKS_TO_DB=true)；click_id=追踪令牌",
            },
            {
                "id": "A3",
                "step": "确认 Redis 可用（clicks 队列入库依赖 Redis）",
                "verify": "redis-cli PING 返回 PONG；或应用启动无 Redis 连接错误",
            },
        ],
    },
    {
        "phase": "B. 短链 → 桥页 → 点击落库",
        "items": [
            {
                "id": "B1",
                "step": "选一条已绑定 Offer+渠道的短链，浏览器无痕访问 /s/{short_code}",
                "verify": "302/桥页正常，URL 中含 click_id（令牌形态，非纯时间戳随机）",
            },
            {
                "id": "B2",
                "step": "完成桥页 /change → /report（或真实跳转链路），记录 click_id",
                "verify": "斗篷上报 200；click_id 与地址栏/网络请求一致",
            },
            {
                "id": "B3",
                "step": "等待 clicks 批量任务或数秒后查库",
                "verify": "sql/verify_dual_track_prerelease.sql 第 2 节：clicks 表有该 click_id",
            },
            {
                "id": "B4",
                "step": "管理后台 → 短链接访问记录，用 click_id 搜索",
                "verify": "列表能查到且 Offer/渠道与短链配置一致",
            },
        ],
    },
    {
        "phase": "C. Postback 归因（令牌优先）",
        "items": [
            {
                "id": "C1",
                "step": "用 B 步得到的 click_id 模拟/真实打 Postback（含 click_id 参数）",
                "verify": "返回成功；postback_conversions 新增一条",
            },
            {
                "id": "C2",
                "step": "查 postback_conversions 归因快照列",
                "verify": "offer_id、publisher_id、advertiser_id、click_time 非空（与令牌一致）",
            },
            {
                "id": "C3",
                "step": "管理后台 → Postback 转化列表，按 conversion_id 或 click_id 筛选",
                "verify": "展示 Offer/渠道/广告主名称正确（快照或 clicks 兜底）",
            },
            {
                "id": "C4",
                "step": "（可选）临时删掉 clicks 中该 click_id 行后重放同 click_id Postback",
                "verify": "仍能归因成功（证明令牌路径生效，不依赖 clicks 行）",
            },
        ],
    },
    {
        "phase": "D. 定时任务与归档",
        "items": [
            {
                "id": "D1",
                "step": "确认定时任务「clicks 批量处理」在跑且未 skipped",
                "verify": "任务日志 processed>0 或队列长度下降；非 skipped:true（双轨下不应跳过）",
            },
            {
                "id": "D2",
                "step": "确认 clicks 归档任务行为符合预期（有数据时正常归档，非误跳过生产数据）",
                "verify": "仅当 USE_TRACKING_TOKEN=true 且 clicks 表为空且未强制写库时才跳过归档",
            },
        ],
    },
    {
        "phase": "E. 回归与收尾",
        "items": [
            {
                "id": "E1",
                "step": "跑自动化门控",
                "verify": "python tests/dual_track_prerelease_checklist.py --auto 全部 passed",
            },
            {
                "id": "E2",
                "step": "跑全量单元测试",
                "verify": "pytest tests/ -q",
            },
            {
                "id": "E3",
                "step": "抽查转化总览 / Cap 扣量是否与双轨数据一致",
                "verify": "转化数、点击数与 DB 抽样一致，无大面积 NULL 归因",
            },
        ],
    },
]

_ENV_REQUIRED = {
    "USE_TRACKING_TOKEN": {"true", "1", "yes"},
    "PERSIST_CLICKS_TO_DB": {"true", "1", "yes"},
}
_ENV_REQUIRED_NONEMPTY = ("AD_TRACKING_MASTER_KEY_HEX",)
_KEY_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

_PYTEST_FILES = [
    "tests/test_dual_track_smoke.py",
    "tests/test_dual_track_prerelease_gates.py",
    "tests/test_click_persist.py",
    "tests/test_tracking_token_integration.py",
    "tests/test_cloak_click_persist.py",
    "tests/test_click_associator_token.py",
    "tests/test_conversion_saver_attribution.py",
    "tests/test_ad_tracking_codec_production_key.py",
]


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def validate_env_file(env_path: Path | None = None) -> list[str]:
    """返回错误列表；空列表表示通过。"""
    path = env_path or (ROOT / ".env")
    errors: list[str] = []
    if not path.is_file():
        errors.append(f"未找到 .env: {path}")
        return errors

    env = _parse_env_file(path)
    for key, allowed in _ENV_REQUIRED.items():
        val = env.get(key, "").lower()
        if val not in allowed:
            errors.append(f"{key} 应为 true/1/yes，当前未满足（请勿在日志中打印密钥）")

    for key in _ENV_REQUIRED_NONEMPTY:
        val = env.get(key, "")
        if not val:
            errors.append(f"{key} 未设置或为空")
        elif key == "AD_TRACKING_MASTER_KEY_HEX" and not _KEY_HEX_PATTERN.match(val):
            errors.append(f"{key} 应为 64 位十六进制")

    return errors


def print_manual_checklist() -> None:
    print("=" * 72)
    print("预发双轨验证清单（人工步骤）")
    print("配置：USE_TRACKING_TOKEN=true + PERSIST_CLICKS_TO_DB=true")
    print("SQL 参考：sql/verify_dual_track_prerelease.sql")
    print("=" * 72)
    for block in MANUAL_CHECKLIST:
        print(f"\n## {block['phase']}")
        for item in block["items"]:
            print(f"  [{item['id']}] {item['step']}")
            print(f"       验收：{item['verify']}")
    print("\n" + "=" * 72)


def run_automated_gates() -> int:
    cmd = [sys.executable, "-m", "pytest", *_PYTEST_FILES, "-v", "--tb=short"]
    print("运行自动化门控:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="预发双轨验证清单")
    parser.add_argument("--env", action="store_true", help="校验项目根 .env 双轨关键项")
    parser.add_argument("--auto", action="store_true", help="运行 pytest 自动化门控")
    parser.add_argument("--all", action="store_true", help="打印清单 + --env + --auto")
    args = parser.parse_args()

    if args.all or not (args.env or args.auto):
        print_manual_checklist()

    exit_code = 0
    if args.env or args.all:
        print("\n--- .env 双轨关键项校验 ---")
        errs = validate_env_file()
        if errs:
            for e in errs:
                print(f"  [FAIL] {e}")
            exit_code = 1
        else:
            print("  [OK] USE_TRACKING_TOKEN / PERSIST_CLICKS_TO_DB / AD_TRACKING_MASTER_KEY_HEX")

    if args.auto or args.all:
        print()
        code = run_automated_gates()
        exit_code = exit_code or code

    if not (args.env or args.auto or args.all):
        print("\n提示: --env 校验配置 | --auto 跑测试 | --all 全部")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
