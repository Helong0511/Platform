"""
智索（Zhisuo）渠道 API 联调脚本。

按 clientId + key 签名，请求 channeldaily / channelcountry / channelunit 等报表接口。
凭证从项目根目录 .env 读取（ZHISUO_API_CLIENT_ID / KEY 及 _2~_4）。

用法:
  python tests/API/zhisuo.py
  python tests/API/zhisuo.py --product wo.kimdogtrainer.com --start-date 2026-06-28 --end-date 2026-06-29
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.core.config import settings

DAY_REPORT = "/api/channeldaily"
COUNTRY_REPORT = "/api/channelcountry"
UNIT_REPORT = "/api/channelunit"

ENDPOINTS = [
    ("每日报告", DAY_REPORT),
    ("国家报告", COUNTRY_REPORT),
    ("广告单元报告", UNIT_REPORT),
]

DEFAULT_PRODUCT = "wo.kimdogtrainer.com"
DEFAULT_START = "2026-06-28"
DEFAULT_END = "2026-06-29"


def build_sign(params: dict[str, Any]) -> str:
    sorted_params = sorted(params.items())
    query = "&".join(f"{k}={v}" for k, v in sorted_params)
    return hashlib.md5(query.encode("utf-8")).hexdigest()


def call_api(
    base_url: str,
    path: str,
    *,
    client_id: str,
    api_key: str,
    start_date: str,
    end_date: str,
    page: int = 1,
    limit: int = 1000,
) -> tuple[int, dict[str, Any]]:
    timestamp = int(time.time() * 1000)
    sign_params = {
        "clientId": client_id,
        "start_date": start_date,
        "end_date": end_date,
        "timestamp": timestamp,
        "limit": limit,
        "page": page,
        "key": api_key,
    }
    sign = build_sign(sign_params)
    request_params = {k: v for k, v in sign_params.items() if k != "key"}
    request_params["sign"] = sign
    resp = requests.get(base_url.rstrip("/") + path, params=request_params, timeout=60)
    return resp.status_code, resp.json()


def fetch_all_rows(
    base_url: str,
    path: str,
    *,
    client_id: str,
    api_key: str,
    start_date: str,
    end_date: str,
    limit: int = 1000,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    all_rows: list[dict[str, Any]] = []
    page = 1
    total_pages = 1
    last_meta: dict[str, Any] = {"code": 1}

    while page <= total_pages:
        http_status, data = call_api(
            base_url,
            path,
            client_id=client_id,
            api_key=api_key,
            start_date=start_date,
            end_date=end_date,
            page=page,
            limit=limit,
        )
        last_meta = data
        if http_status != 200 or data.get("code") != 1:
            return data, all_rows

        block = data.get("data") or {}
        rows = block.get("list") or []
        if isinstance(rows, list):
            all_rows.extend(rows)
        total_pages = int(block.get("total_pages") or 1)
        page += 1

    return last_meta, all_rows


def row_product_name(row: dict[str, Any]) -> str:
    return str(row.get("product_name") or row.get("domain_name") or "").strip()


def match_product(row: dict[str, Any], product: str) -> bool:
    needle = product.strip().lower()
    if not needle:
        return True
    name = row_product_name(row).lower()
    return needle in name or name in needle


def summarize_rows(rows: list[dict[str, Any]], product: str) -> dict[str, list[dict[str, Any]]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not match_product(row, product):
            continue
        date_key = str(row.get("date") or "").strip()
        by_date.setdefault(date_key, []).append(row)
    return by_date


def print_account_probe(
    *,
    base_url: str,
    account: dict[str, Any],
    start_date: str,
    end_date: str,
    product: str,
) -> None:
    client_id = str(account["client_id"])
    api_key = str(account["api_key"])
    fetch_unit = bool(account.get("fetch_unit"))
    fetch_country = bool(account.get("fetch_country"))

    print("=" * 70)
    print(f"账号: {client_id}  |  fetch_unit={fetch_unit}  fetch_country={fetch_country}")
    print(f"日期: {start_date} ~ {end_date}  |  产品: {product}")
    print("=" * 70)

    for name, path in ENDPOINTS:
        if path == UNIT_REPORT and not fetch_unit:
            print(f"\n【{name}】跳过（账号未开启 fetch_unit）")
            continue
        if path == COUNTRY_REPORT and not fetch_country:
            print(f"\n【{name}】跳过（账号未开启 fetch_country）")
            continue

        print(f"\n【{name}】 GET {path}")
        try:
            meta, rows = fetch_all_rows(
                base_url,
                path,
                client_id=client_id,
                api_key=api_key,
                start_date=start_date,
                end_date=end_date,
            )
            code = meta.get("code")
            msg = meta.get("msg", "")
            ok = code == 1
            print(f"  code={code}  msg={msg}  全量行数={len(rows)}  {'[OK]' if ok else '[FAIL]'}")

            matched = [r for r in rows if match_product(r, product)]
            print(f"  匹配产品「{product}」: {len(matched)} 条")

            if matched:
                by_date = summarize_rows(matched, product)
                for date_key in sorted(by_date):
                    day_rows = by_date[date_key]
                    print(f"    {date_key}: {len(day_rows)} 条")
                    for row in day_rows[:3]:
                        print("      " + json.dumps(row, ensure_ascii=False))
                    if len(day_rows) > 3:
                        print(f"      ... 另有 {len(day_rows) - 3} 条")
            elif rows and ok:
                sample_products = sorted({row_product_name(r) for r in rows if row_product_name(r)})[:10]
                if sample_products:
                    print(f"  该日期范围内其它产品样例: {', '.join(sample_products)}")
        except Exception as exc:
            print(f"  [FAIL] 异常: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="智索 API 多账号联调")
    parser.add_argument("--start-date", default=DEFAULT_START)
    parser.add_argument("--end-date", default=DEFAULT_END)
    parser.add_argument("--product", default=DEFAULT_PRODUCT)
    args = parser.parse_args()

    base_url = settings.ZHISUO_API_BASE_URL or "https://ch.tecnee.xyz"
    accounts = settings.get_zhisuo_accounts()
    if not accounts:
        raise RuntimeError(
            "未配置 zhisuo 账号，请在 .env 设置 ZHISUO_API_CLIENT_ID/KEY 及 _2~_4"
        )

    print(f"Base URL: {base_url}")
    print(f"已加载 {len(accounts)} 个账号: {', '.join(str(a['client_id']) for a in accounts)}\n")

    for account in accounts:
        print_account_probe(
            base_url=base_url,
            account=account,
            start_date=args.start_date,
            end_date=args.end_date,
            product=args.product,
        )
        print()


if __name__ == "__main__":
    main()
