"""
yangyangdeyi（通百世家 TBSJ）API 联调脚本 — 拉取今天数据。

流程：POST /token 获取 access_token → 请求 adunit / unit_data / country。
凭证优先从环境变量 TBSJ_API_USERNAME / TBSJ_API_PASSWORD 读取。
"""
import json
import os
import sys
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://data.tongbaishijia.com/api/thirdservice"
HEADERS = {"Content-Type": "application/json;charset=utf-8"}

USERNAME = os.getenv("TBSJ_API_USERNAME", "BOFIT1")
PASSWORD = os.getenv("TBSJ_API_PASSWORD", "")

ENDPOINTS = [
    ("广告单元 adunit", "/adunit"),
    ("单元明细 unit_data", "/unit_data"),
    ("国家 country", "/country"),
]

today = date.today().isoformat()
START = f"{today} 00:00:00"
END = f"{today} 23:59:59"


def get_access_token() -> str:
    resp = requests.post(
        BASE_URL + "/token",
        json={"username": USERNAME, "password": PASSWORD},
        headers=HEADERS,
        timeout=60,
        verify=False,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token") or data.get("data", {}).get("access_token")
    if not token:
        raise RuntimeError(f"未获取到 access_token: {data}")
    return token


def call_api(path: str, token: str, *, page: int = 1, limit: int = 5):
    auth_headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    payload = {
        "page": page,
        "limit": limit,
        "start": START,
        "end": END,
    }
    resp = requests.post(
        BASE_URL + path,
        json=payload,
        headers=auth_headers,
        timeout=60,
        verify=False,
    )
    return resp.status_code, resp.json()


def extract_items(data: dict) -> list:
    if isinstance(data.get("data"), dict):
        return data["data"].get("items") or data["data"].get("list") or []
    return data.get("items") or data.get("list") or []


def main():
    if not PASSWORD:
        print("错误: 请设置 TBSJ_API_PASSWORD（.env 或环境变量）")
        sys.exit(1)

    print(f"账号: {USERNAME}")
    print(f"日期: {today} ({START} ~ {END})\n")

    try:
        token = get_access_token()
        print("[OK] Token 获取成功\n")
    except Exception as e:
        print(f"[FAIL] Token 获取失败: {e}")
        sys.exit(1)

    for name, path in ENDPOINTS:
        print("=" * 60)
        print(f"【{name}】 POST {path}")
        print("=" * 60)
        try:
            status, data = call_api(path, token, page=1, limit=5)
            code = data.get("code")
            msg = data.get("msg") or data.get("message") or ""
            ok = status == 200 and code == 20000
            print(f"HTTP: {status}  |  code: {code}  |  msg: {msg}")
            print(f"结果: {'[OK] 成功' if ok else '[FAIL] 失败'}")

            items = extract_items(data)
            block = data.get("data") if isinstance(data.get("data"), dict) else {}
            total = block.get("total") or block.get("count") or len(items)
            print(f"total={total}, 本页条数={len(items)}")
            if items:
                print(f"字段: {list(items[0].keys())}")
                print("首条样例:")
                print(json.dumps(items[0], ensure_ascii=False, indent=2))
            else:
                print("items 为空（今天可能暂无数据）")
        except Exception as e:
            print(f"[FAIL] 异常: {e}")
        print()

    print("=" * 60)
    print("【全量分页统计 - adunit】")
    print("=" * 60)
    try:
        all_rows = []
        page = 1
        total = 0
        while True:
            _, data = call_api("/adunit", token, page=page, limit=1000)
            if data.get("code") != 20000:
                print(f"拉取失败: {data}")
                break
            block = data.get("data") or {}
            rows = extract_items(data)
            total = int(block.get("total") or total)
            all_rows.extend(rows)
            if not rows or (total > 0 and len(all_rows) >= total):
                break
            page += 1
        print(f"adunit 今天共 {len(all_rows)} 条 (API total={total}, 分页 {page} 页)")
    except Exception as e:
        print(f"异常: {e}")


if __name__ == "__main__":
    main()
