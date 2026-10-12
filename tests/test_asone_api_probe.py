"""Asone API 连通性探测（测试用，不入库）。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date, timedelta

import os
import sys

API_KEY = (os.getenv("ASONE_API_KEY") or "").strip()
BASE = os.getenv("ASONE_API_BASE_URL", "https://asone.club").rstrip("/")
if not API_KEY:
    print("请设置环境变量 ASONE_API_KEY 后再运行", file=sys.stderr)
    raise SystemExit(2)

ENDPOINTS = {
    "unit": "/api/channel-unit-report/apiPage",
    "country": "/api/channel-country-report/apiPage",
    "daily": "/api/channel-daily-report/apiPage",
    # 文档名「明细」，路径为 channel-data-report（非 channel-detail-report）
    "detail": "/api/channel-data-report/apiPage",
}


def post(path: str, payload: dict) -> tuple[int, dict | str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def main() -> None:
    today = date.today()
    ranges = [
        (today - timedelta(days=7), today),
        (today - timedelta(days=30), today),
        (date(2026, 8, 1), date(2026, 8, 31)),
        (date(2025, 1, 1), today),
    ]
    print(f"BASE={BASE}")
    for name, path in ENDPOINTS.items():
        print(f"\n==== {name} {path} ====")
        for start, end in ranges:
            payload = {
                "current": 1,
                "size": 5,
                "reportDateStart": start.isoformat(),
                "reportDateEnd": end.isoformat(),
                "orders": [{"column": "reportDate", "asc": False}],
            }
            status, data = post(path, payload)
            if isinstance(data, dict):
                total = (data.get("data") or {}).get("total")
                records = (data.get("data") or {}).get("records") or []
                print(
                    f"{start}~{end} status={status} success={data.get('success')} "
                    f"code={data.get('code')} total={total} msg={data.get('message')}"
                )
                if records:
                    print("sample keys:", sorted(records[0].keys()))
                    print("sample:", json.dumps(records[0], ensure_ascii=False, indent=2))
                    break
            else:
                print(f"{start}~{end} status={status} raw={data[:300]}")


if __name__ == "__main__":
    main()
