"""探测各上游 API 分页字段与首屏条数（只读，不写库）。"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytz
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

TZ = pytz.timezone(os.getenv("TIMEZONE", "Asia/Shanghai"))
TODAY = datetime.now(TZ).strftime("%Y-%m-%d")
YESTERDAY = (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")


def _keys(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield prefix + k
            yield from _keys(v, prefix + k + ".")
    elif isinstance(obj, list) and obj and isinstance(obj[0], dict):
        yield from _keys(obj[0], prefix + "[0].")


def summarize(label: str, data: dict, row_paths: list[str]):
    print(f"\n=== {label} ===")
    interesting = [
        k
        for k in _keys(data)
        if any(
            x in k.lower()
            for x in ("total", "page", "count", "limit", "size", "rows", "list", "items")
        )
    ]
    print("分页相关字段:", sorted(set(interesting))[:30])
    for path in row_paths:
        cur = data
        for part in path.split("."):
            if part == "data" and isinstance(cur, dict) and "data" in cur:
                cur = cur["data"]
            elif isinstance(cur, dict):
                cur = cur.get(part)
            else:
                cur = None
                break
        n = len(cur) if isinstance(cur, list) else "N/A"
        print(f"  {path} 条数={n}")
    # 打印常见分页元数据
    block = data.get("data") if isinstance(data.get("data"), dict) else data
    for k in ("total", "totalRow", "totalPage", "total_pages", "page", "count", "ret", "code", "state", "status", "msg"):
        if k in data:
            print(f"  {k}={data[k]!r}")
        if isinstance(block, dict) and k in block:
            print(f"  data.{k}={block[k]!r}")
    print("顶层 keys:", list(data.keys())[:20])


def probe_tqt():
    app_key = os.getenv("TQT_APP_KEY", "")
    secret = os.getenv("TQT_API_SECRET", "")
    if not app_key:
        print("TQT 未配置，跳过")
        return
    week_ago = (datetime.now(TZ) - timedelta(days=7)).strftime("%Y-%m-%d")
    for start, end in ((YESTERDAY, TODAY), (week_ago, TODAY)):
        params = {
            "appKey": app_key,
            "startDate": start,
            "endDate": end,
            "page": 1,
            "pageSize": 1000,
            "type": "country",
        }
        sorted_items = sorted((k, v) for k, v in params.items() if k != "sign")
        query_str = "".join(f"{k}{v}" for k, v in sorted_items)
        params["sign"] = hashlib.md5(f"{secret}{query_str}{secret}".lower().encode()).hexdigest()
        r = requests.post(
            "https://union.e-kivi.com/open/api/report/data",
            json=params,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=60,
        )
        data = r.json()
        print(f"\n--- TQT range={start}~{end} ---")
        summarize("TQT", data, ["data.list", "list"])
        block = data.get("data") or {}
        total_page = int(block.get("totalPage") or 1)
        if total_page > 1:
            params["page"] = 2
            sorted_items = sorted((k, v) for k, v in params.items() if k != "sign")
            query_str = "".join(f"{k}{v}" for k, v in sorted_items)
            params["sign"] = hashlib.md5(f"{secret}{query_str}{secret}".lower().encode()).hexdigest()
            r2 = requests.post(
                "https://union.e-kivi.com/open/api/report/data",
                json=params,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=60,
            ).json()
            lst2 = (r2.get("data") or {}).get("list") or []
            print(f"  page2 list 条数={len(lst2)}")


def probe_skymobi():
    api_id = os.getenv("SKYMOBI_API_ID", "")
    api_key = os.getenv("SKYMOBI_API_KEY", "")
    if not api_id:
        print("Skymobi 未配置，跳过")
        return
    for date_str in (TODAY, YESTERDAY):
        url = (
            f"https://crm.skymobi.online/api/adxh5"
            f"?apikey={api_key}&date={date_str}&uid={api_id}&page=1&limit=1000"
        )
        r = requests.post(url, timeout=60)
        data = r.json()
        print(f"\n--- Skymobi date={date_str} ---")
        summarize("Skymobi", data, ["list"])
        # 探测 page=2
        url2 = url.replace("page=1", "page=2")
        r2 = requests.post(url2, timeout=60).json()
        lst2 = r2.get("list") or []
        print(f"  page2 list 条数={len(lst2) if isinstance(lst2, list) else 'N/A'}")


def probe_addermobi():
    user = os.getenv("ADDERMOBI_API_USERNAME", "")
    pwd = os.getenv("ADDERMOBI_API_PASSWORD", "")
    if not user:
        print("Addermobi 未配置，跳过")
        return
    login = requests.post(
        "https://api.addermobi.com/api/User/loginApi",
        json={"userName": user, "password": pwd},
        timeout=60,
        verify=False,
    ).json()
    token = (login.get("data") or {}).get("token") or login.get("token")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    wheres = [
        {"name": "Revenue_time", "value": YESTERDAY, "displayType": "thanorequal"},
        {"name": "Revenue_time", "value": TODAY, "displayType": "lessorequal"},
    ]
    payload = {
        "page": 1,
        "rows": 1000,
        "sort": "Revenue_time,Product_id",
        "order": "desc",
        "wheres": json.dumps(wheres),
    }
    r = requests.post(
        "https://api.addermobi.com/api/Revenue_DetailReports/GetData",
        json=payload,
        headers=headers,
        timeout=60,
        verify=False,
    )
    data = r.json()
    summarize("Addermobi", data, ["rows", "data", "list"])


def probe_huguang():
    key = os.getenv("HUGUANG_API_KEY", "")
    domain = os.getenv("HUGUANG_API_DOMAIN", "")
    username = os.getenv("HUGUANG_API_USERNAME", "")
    if not key:
        print("Huguang 未配置，跳过")
        return
    r = requests.post(
        f"http://{domain}:5858/api/country",
        json={"key": key, "startdate": YESTERDAY, "enddate": TODAY, "username": username},
        timeout=60,
        verify=False,
    )
    data = r.json()
    summarize("Huguang", data, ["data"])


if __name__ == "__main__":
    print(f"探测日期: {YESTERDAY} ~ {TODAY}")
    probe_tqt()
    probe_skymobi()
    probe_addermobi()
    probe_huguang()
