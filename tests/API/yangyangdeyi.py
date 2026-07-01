"""
yangyangdeyi（通百世家 TBSJ）API 联调脚本 — 与生产定时任务 tbsj_api_task 对齐。

流程：POST /token 获取 access_token → 全量分页拉取 /adunit。
凭证：项目根目录 .env 中 TBSJ_API_USERNAME / TBSJ_API_PASSWORD。
日期：resolve_upstream_date_range(early_morning_dual_day=True)，格式 00:00:00 ~ 23:59:59。

用法:
  python tests/API/yangyangdeyi.py
  python tests/API/yangyangdeyi.py --start-date 2026-06-12 --end-date 2026-06-13
  python tests/API/yangyangdeyi.py --probe-extra   # 额外探测 unit_data / country（生产未接入）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.core.config import settings
from app.scheduler_module.task_utils import resolve_upstream_date_range
from app.scheduler_module.tasks.tbsj_task import TBSJ_FIELD_MAPPING, TBSJ_HEADERS, TBSJ_URL
from app.scheduler_module.upstream_fetch import (
    _should_break_upstream_pagination,
    format_tbsj_datetime_range,
)

PAGE_LIMIT = 1000
ADUNIT_PATH = "/adunit"
PROBE_ENDPOINTS = [
    ("单元明细 unit_data", "/unit_data"),
    ("国家 country", "/country"),
]


def get_access_token() -> str:
    username = settings.TBSJ_API_USERNAME
    password = settings.TBSJ_API_PASSWORD
    if not username or not password:
        raise RuntimeError("请在 .env 配置 TBSJ_API_USERNAME / TBSJ_API_PASSWORD")

    resp = requests.post(
        TBSJ_URL + "/token",
        json={"username": username, "password": password},
        headers=TBSJ_HEADERS,
        timeout=60,
        verify=False,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token") or (data.get("data") or {}).get("access_token")
    if not token:
        raise RuntimeError(f"未获取到 access_token: {data}")
    return token


def call_adunit(
    token: str,
    *,
    start_at: str,
    end_at: str,
    page: int = 1,
    limit: int = PAGE_LIMIT,
) -> tuple[int, dict]:
    auth_headers = {**TBSJ_HEADERS, "Authorization": f"Bearer {token}"}
    payload = {
        "page": page,
        "limit": limit,
        "start": start_at,
        "end": end_at,
    }
    resp = requests.post(
        TBSJ_URL + ADUNIT_PATH,
        json=payload,
        headers=auth_headers,
        timeout=60,
        verify=False,
    )
    return resp.status_code, resp.json()


def fetch_adunit_all(token: str, start_date: str, end_date: str) -> tuple[list, int, int]:
    """与 fetch_tbsj_rows 一致：/adunit 全量分页。"""
    start_at, end_at = format_tbsj_datetime_range(start_date, end_date)
    all_rows: list = []
    page = 1
    total = 0

    while True:
        status, data = call_adunit(
            token,
            start_at=start_at,
            end_at=end_at,
            page=page,
            limit=PAGE_LIMIT,
        )
        if status != 200 or data.get("code") != 20000:
            raise RuntimeError(f"adunit 拉取失败 (page={page}): HTTP {status}, body={data}")

        block = data.get("data") or {}
        if not isinstance(block, dict):
            break

        rows = block.get("items") or []
        if isinstance(rows, list):
            all_rows.extend(rows)

        total = int(block.get("total") or total)
        if _should_break_upstream_pagination(
            rows,
            total=total,
            collected=len(all_rows),
            page=page,
            total_pages=0,
            limit=limit,
        ):
            break
        page += 1

    return all_rows, total, page


def probe_endpoint(token: str, path: str, start_at: str, end_at: str) -> None:
    auth_headers = {**TBSJ_HEADERS, "Authorization": f"Bearer {token}"}
    payload = {"page": 1, "limit": 5, "start": start_at, "end": end_at}
    resp = requests.post(
        TBSJ_URL + path,
        json=payload,
        headers=auth_headers,
        timeout=60,
        verify=False,
    )
    data = resp.json()
    code = data.get("code")
    msg = data.get("msg") or data.get("message") or ""
    ok = resp.status_code == 200 and code == 20000
    print(f"HTTP: {resp.status_code}  |  code: {code}  |  msg: {msg}")
    print(f"结果: {'[OK] 成功' if ok else '[FAIL] 失败'}")

    block = data.get("data") if isinstance(data.get("data"), dict) else {}
    items = block.get("items") or block.get("list") or []
    total = block.get("total") or block.get("count") or len(items)
    print(f"total={total}, 本页条数={len(items)}")
    if items:
        print(f"字段: {list(items[0].keys())}")
        print("首条样例:")
        print(json.dumps(items[0], ensure_ascii=False, indent=2))
    else:
        print("items 为空")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="yangyangdeyi TBSJ API 联调（对齐生产 tbsj_api_task）")
    parser.add_argument("--start-date", help="开始日期 YYYY-MM-DD（默认与定时任务相同）")
    parser.add_argument("--end-date", help="结束日期 YYYY-MM-DD（默认与定时任务相同）")
    parser.add_argument(
        "--probe-extra",
        action="store_true",
        help="额外探测 unit_data / country（生产定时任务未接入）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_date, end_date = resolve_upstream_date_range(
        args.start_date,
        args.end_date,
        early_morning_dual_day=True,
    )
    start_at, end_at = format_tbsj_datetime_range(start_date, end_date)

    print(f"Base URL: {TBSJ_URL}")
    print(f"账号: {settings.TBSJ_API_USERNAME}")
    print(f"拉数区间: {start_date} ~ {end_date}")
    print(f"API 时间: {start_at} ~ {end_at}")
    print(f"生产接口: POST {ADUNIT_PATH} (limit={PAGE_LIMIT})")
    print(f"字段映射: {json.dumps(TBSJ_FIELD_MAPPING, ensure_ascii=False)}\n")

    try:
        token = get_access_token()
        print("[OK] Token 获取成功\n")
    except Exception as e:
        print(f"[FAIL] Token 获取失败: {e}")
        sys.exit(1)

    if args.probe_extra:
        for name, path in PROBE_ENDPOINTS:
            print("=" * 60)
            print(f"【探测 {name}】 POST {path}（非生产路径）")
            print("=" * 60)
            try:
                probe_endpoint(token, path, start_at, end_at)
            except Exception as e:
                print(f"[FAIL] 异常: {e}")
            print()

    print("=" * 60)
    print("【全量分页 - adunit】（与生产 fetch_tbsj_rows 一致）")
    print("=" * 60)
    try:
        all_rows, total, pages = fetch_adunit_all(token, start_date, end_date)
        print(f"adunit 共 {len(all_rows)} 条 (API total={total}, 分页 {pages} 页)")
        if all_rows:
            print(f"字段: {list(all_rows[0].keys())}")
            print("首条样例:")
            print(json.dumps(all_rows[0], ensure_ascii=False, indent=2))
        else:
            print("items 为空（该日期区间可能暂无数据）")
    except Exception as e:
        print(f"[FAIL] 异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
