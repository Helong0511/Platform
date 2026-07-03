"""GAM 拉数诊断：复现 TypeError 并打印完整堆栈。"""
from __future__ import annotations

import json
import os
import traceback
from datetime import date

from app.scheduler_module.gam_fetch import run_gam_fetch_to_memory
from app.scheduler_module.gam_scheduler_config import (
    get_gam_scheduler_config_path,
    resolve_gam_scheduler_accounts,
)


def main() -> None:
    config_path = get_gam_scheduler_config_path()
    print(f"配置文件: {config_path} (exists={config_path.is_file()})")
    if os.getenv("GAM_ACCOUNTS"):
        print("环境变量 GAM_ACCOUNTS 已设置（将覆盖默认账号来源时需传 accounts=None 才生效）")

    accounts = resolve_gam_scheduler_accounts() or []
    if not accounts:
        print("未加载到 GAM 账号")
        return

    for index, account in enumerate(accounts):
        report_keys = account.get("report_keys")
        whitelist = account.get("product_whitelist")
        print(
            f"[{index}] key={account.get('key')} "
            f"report_keys={report_keys!r} (type={type(report_keys).__name__}) "
            f"whitelist_len={len(whitelist or [])}"
        )
        if isinstance(report_keys, (int, float)):
            print("  !! report_keys 为数字，旧代码会触发 TypeError: 'int' object is not iterable")

    print("\n开始 run_gam_fetch_to_memory ...")
    try:
        bundles = run_gam_fetch_to_memory(
            date(2026, 7, 2),
            date(2026, 7, 2),
            accounts=accounts,
        )
        print(f"成功: {len(bundles)} 个账号")
        for bundle in bundles:
            reports = bundle.get("reports") or {}
            counts = {key: len(rows) for key, rows in reports.items()}
            print(f"  {bundle.get('account_key')}: {json.dumps(counts, ensure_ascii=False)}")
    except Exception as exc:
        print(f"失败: {type(exc).__name__}: {exc}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
