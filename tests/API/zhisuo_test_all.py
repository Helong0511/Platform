"""
智索 API 三接口联调：每日报告 / 国家报告 / 广告单元报告
"""
import hashlib
import json
import time
from datetime import date, timedelta

import requests

BASE_URL = "https://ch.tecnee.xyz"
CLIENT_ID = "KE11"
API_KEY = "cded7587a3b1aad269b9c9f5248f8b7e"

ENDPOINTS = [
    ("每日报告", "/api/channeldaily"),
    ("国家报告", "/api/channelcountry"),
    ("广告单元报告", "/api/channelunit"),
]

# 最近 7 天
end_date = date.today().isoformat()
start_date = (date.today() - timedelta(days=7)).isoformat()


def build_sign(params: dict) -> str:
    sorted_params = sorted(params.items())
    query = "&".join(f"{k}={v}" for k, v in sorted_params)
    return hashlib.md5(query.encode("utf-8")).hexdigest()


def call_api(path: str, page: int = 1, limit: int = 5):
    timestamp = int(time.time() * 1000)
    sign_params = {
        "clientId": CLIENT_ID,
        "start_date": start_date,
        "end_date": end_date,
        "timestamp": timestamp,
        "limit": limit,
        "page": page,
        "key": API_KEY,
    }
    sign = build_sign(sign_params)
    request_params = {k: v for k, v in sign_params.items() if k != "key"}
    request_params["sign"] = sign
    resp = requests.get(BASE_URL + path, params=request_params, timeout=60)
    return resp.status_code, resp.json()


def fetch_all_pages(path: str, limit: int = 1000):
    all_rows = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        _, data = call_api(path, page=page, limit=limit)
        if data.get("code") != 1:
            return data, all_rows
        block = data.get("data") or {}
        all_rows.extend(block.get("list") or [])
        total_pages = int(block.get("total_pages") or 1)
        page += 1
    return {"code": 1}, all_rows


def main():
    print(f"账号: {CLIENT_ID}")
    print(f"日期: {start_date} ~ {end_date}\n")

    for name, path in ENDPOINTS:
        print("=" * 60)
        print(f"【{name}】 GET {path}")
        print("=" * 60)
        try:
            http_status, data = call_api(path, page=1, limit=5)
            code = data.get("code")
            msg = data.get("msg", "")
            ok = http_status == 200 and code == 1
            print(f"HTTP: {http_status}  |  code: {code}  |  msg: {msg}")
            print(f"结果: {'[OK] 成功' if ok else '[FAIL] 失败'}")

            block = data.get("data") or {}
            if isinstance(block, dict):
                print(f"total={block.get('total')}, total_pages={block.get('total_pages')}, page={block.get('page')}")
                lst = block.get("list") or []
                if lst:
                    print(f"字段: {list(lst[0].keys())}")
                    print("首条样例:")
                    print(json.dumps(lst[0], ensure_ascii=False, indent=2))
                else:
                    print("list 为空（该日期范围内无数据）")
            else:
                print(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[FAIL] 异常: {e}")
        print()

    print("=" * 60)
    print("【全量分页统计】")
    print("=" * 60)
    for name, path in ENDPOINTS:
        try:
            meta, rows = fetch_all_pages(path)
            if meta.get("code") == 1:
                print(f"{name}: 共 {len(rows)} 条")
            else:
                print(f"{name}: 拉取失败 - {meta}")
        except Exception as e:
            print(f"{name}: 异常 - {e}")


if __name__ == "__main__":
    main()
