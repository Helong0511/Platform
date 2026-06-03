"""
Pomiad 上游 API 对接测试
文档: tests/Pomiad_com_data_api.pdf

流程:
1. POST /ys_data/login 获取 token
2. GET  /ys_data/normal/api_data 获取站点列表（site_url）
3. POST /ys_data/normal/data_detail 按 site_url + data_date 拉取明细
"""
import json
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import requests

BASE_URL = "https://data.pomiad.com/ys_data"
LOGIN_URL = f"{BASE_URL}/login"
API_DATA_URL = f"{BASE_URL}/normal/api_data"
DATA_DETAIL_URL = f"{BASE_URL}/normal/data_detail"

USERNAME = "Yic"
PASSWORD = "Yic12356"

API_DATA_LIMIT = 100
TEST_DATES = ["2026-06-01", "2026-06-02"]
IS_BY_COUNTRY = 0
FLOAT_DECIMALS = 6

# 全部 HTTP 交互记录
REQUEST_LOGS: list[dict[str, Any]] = []


def clean_float(value: float) -> float | int:
    quantized = Decimal(str(value)).quantize(
        Decimal(f"1e-{FLOAT_DECIMALS}"),
        rounding=ROUND_HALF_UP,
    )
    normalized = quantized.normalize()
    if normalized == normalized.to_integral_value():
        return int(normalized)
    return float(normalized)


def normalize_numbers(obj: Any) -> Any:
    if isinstance(obj, float):
        return clean_float(obj)
    if isinstance(obj, dict):
        return {k: normalize_numbers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_numbers(v) for v in obj]
    return obj


def format_display_value(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float):
        cleaned = clean_float(val)
        if isinstance(cleaned, int):
            return str(cleaned)
        return f"{cleaned:.{FLOAT_DECIMALS}f}".rstrip("0").rstrip(".")
    return str(val)


def dumps_json(obj: Any) -> str:
    return json.dumps(normalize_numbers(obj), ensure_ascii=False, indent=2)


def dumps_raw_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def mask_sensitive_headers(headers: dict[str, str]) -> dict[str, str]:
    """Authorization 仅展示前后片段"""
    masked = dict(headers)
    auth = masked.get("Authorization") or masked.get("authorization")
    if auth and len(auth) > 20:
        masked["Authorization"] = f"{auth[:12]}...{auth[-8:]} (长度={len(auth)})"
    return masked


def mask_sensitive_body(body: Any) -> Any:
    if isinstance(body, dict) and "password" in body:
        return {**body, "password": "******"}
    return body


def print_section(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(title)
    print("=" * 72)


def print_request_detail(log: dict[str, Any]) -> None:
    """打印单次 HTTP 交互的完整详情"""
    print_section(f"HTTP 详情 #{log['index']} — {log['name']}")

    print(f"时间: {log['timestamp']}")
    print(f"耗时: {log['elapsed_ms']} ms")
    print(f"方法: {log['method']}")
    print(f"URL : {log['url']}")

    print("\n--- 请求 Headers ---")
    print(dumps_raw_json(log["request_headers"]))

    if log.get("query_params"):
        print("\n--- 请求 Query 参数 ---")
        print(dumps_raw_json(log["query_params"]))

    if log.get("request_body") is not None:
        print("\n--- 请求 Body (JSON) ---")
        print(dumps_raw_json(log["request_body"]))

    print(f"\n--- 响应状态 ---")
    print(f"HTTP Status: {log['status_code']} {log.get('reason', '')}")

    if log.get("response_headers"):
        print("\n--- 响应 Headers ---")
        print(dumps_raw_json(log["response_headers"]))

    print("\n--- 响应 Body（原始） ---")
    print(dumps_raw_json(log["response_body"]))


def http_request(
    name: str,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 60,
) -> tuple[requests.Response, Any]:
    """发起请求并记录完整交互信息"""
    headers = headers or {}
    started = time.perf_counter()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    if method.upper() == "GET":
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    else:
        resp = requests.post(url, headers=headers, params=params, json=json_body, timeout=timeout)

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    resp.raise_for_status()

    try:
        response_body = resp.json()
    except ValueError:
        response_body = resp.text

    full_url = resp.url
    log = {
        "index": len(REQUEST_LOGS) + 1,
        "name": name,
        "timestamp": timestamp,
        "elapsed_ms": elapsed_ms,
        "method": method.upper(),
        "url": full_url,
        "request_headers": mask_sensitive_headers(headers),
        "query_params": params,
        "request_body": mask_sensitive_body(json_body),
        "status_code": resp.status_code,
        "reason": resp.reason,
        "response_headers": dict(resp.headers),
        "response_body": response_body,
    }
    REQUEST_LOGS.append(log)
    print_request_detail(log)

    return resp, response_body


def print_config() -> None:
    print_section("测试配置")
    print(dumps_raw_json({
        "BASE_URL": BASE_URL,
        "LOGIN_URL": LOGIN_URL,
        "API_DATA_URL": API_DATA_URL,
        "DATA_DETAIL_URL": DATA_DETAIL_URL,
        "USERNAME": USERNAME,
        "PASSWORD": "******",
        "TEST_DATES": TEST_DATES,
        "IS_BY_COUNTRY": IS_BY_COUNTRY,
        "API_DATA_LIMIT": API_DATA_LIMIT,
    }))


def login() -> str:
    _, body = http_request(
        "登录 login",
        "POST",
        LOGIN_URL,
        headers={"Content-Type": "application/json"},
        json_body={"username": USERNAME, "password": PASSWORD},
        timeout=30,
    )
    if body.get("rtn") != 200:
        raise RuntimeError(f"登录失败: rtn={body.get('rtn')}, body={body}")
    token = body.get("token")
    if not token:
        raise RuntimeError(f"登录成功但未返回 token: {body}")
    print(f"\nToken 获取成功 (长度={len(token)}, expire={body.get('expire')})")
    return token


def fetch_api_data_all(token: str, start_at: str, end_at: str) -> list[dict]:
    all_rows: list[dict] = []
    page = 1
    while True:
        params = {
            "page": page,
            "limit": API_DATA_LIMIT,
            "start_at": start_at,
            "end_at": end_at,
        }
        _, body = http_request(
            f"站点汇总 api_data (page={page})",
            "GET",
            API_DATA_URL,
            headers={"Authorization": token},
            params=params,
        )
        if body.get("rtn") != 200:
            raise RuntimeError(f"api_data 请求失败: {body}")

        wrapper = body.get("data") or {}
        rows = wrapper.get("data") or []
        all_rows.extend(rows)

        total = wrapper.get("count", 0)
        if len(all_rows) >= total or not rows:
            break
        page += 1

    return all_rows


def fetch_data_detail(
    token: str,
    site_url: str,
    data_date: str,
    is_by_country: int = IS_BY_COUNTRY,
) -> dict:
    payload = {
        "site_url": site_url,
        "data_date": data_date,
        "is_by_country": is_by_country,
    }
    _, body = http_request(
        f"明细 data_detail ({site_url} @ {data_date})",
        "POST",
        DATA_DETAIL_URL,
        headers={"Authorization": token, "Content-Type": "application/json"},
        json_body=payload,
    )
    return body


def _collect_keys(rows: list[dict]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row.keys():
            if k not in seen:
                seen.add(k)
                keys.append(k)
    return keys


def print_full_table(title: str, rows: list[dict]) -> None:
    if not rows:
        print(f"\n=== {title}：无数据 ===")
        return

    normalized_rows = normalize_numbers(rows)
    keys = _collect_keys(normalized_rows)
    col_widths = {
        k: max(len(k), *(len(format_display_value(r.get(k))) for r in normalized_rows))
        for k in keys
    }

    print_section(f"{title}（共 {len(normalized_rows)} 条，字段 {len(keys)} 个）")
    header = " | ".join(k.ljust(col_widths[k]) for k in keys)
    print(header)
    print("-" * len(header))
    for row in normalized_rows:
        print(" | ".join(
            format_display_value(row.get(k)).ljust(col_widths[k]) for k in keys
        ))


def print_all_records_json(title: str, rows: list[dict], *, raw: bool = False) -> None:
    label = "原始" if raw else "规范化"
    print_section(f"{title} {label} JSON（共 {len(rows)} 条）")
    dump_fn = dumps_raw_json if raw else dumps_json
    for i, row in enumerate(rows, 1):
        print(f"\n--- 第 {i} 条 ---")
        print(dump_fn(row))


def print_field_mapping_all(rows: list[dict]) -> None:
    """平台入库字段映射 + 比率字段说明"""
    mappings = []
    for row in rows:
        req = row.get("ad_request") or 0
        match = row.get("match_count") or 0
        imps = row.get("imps") or 0
        clicks = row.get("clicks") or 0

        # 平台入库时会根据数量自动计算比率（process_api_ad_data → calculate_rates）
        calc_coverage = round(match / req * 100, 2) if req > 0 else 0.0      # 覆盖率 = 匹配数/请求数
        calc_display = round(imps / match * 100, 2) if match > 0 else 0.0   # 展示率 = 展示数/匹配数
        calc_click = round(clicks / imps * 100, 2) if imps > 0 else 0.0      # 点击率 = 点击数/展示数

        mappings.append(normalize_numbers({
            # --- 直接映射入库 ---
            "date": row.get("data_date_f"),                              # 日期 ← data_date_f
            "product_name": row.get("domain_name") or row.get("site"),   # 产品/站点 ← domain_name
            "ad_unit": row.get("ad_unit_name"),                          # 广告单元 ← ad_unit_name
            "country_code": row.get("country_name") or row.get("country_code"),  # 国家 ← country_name
            "request_count": req,                                        # 请求数 ← ad_request
            "match_count": match,                                        # 匹配数 ← match_count
            "display_count": imps,                                       # 展示数 ← imps
            "click_count": clicks,                                       # 点击数 ← clicks
            "revenue_before_deduct": row.get("final_revenue"),           # 收益 ← final_revenue（分成后）
            "ecpm_before_deduct": row.get("cpm"),                        # eCPM ← cpm
            "cpc": row.get("cpc"),                                       # CPC ← cpc
            # --- 平台自动计算（不入 API 映射，入库时由数量算出）---
            "coverage_rate": calc_coverage,                              # 覆盖率 = 匹配数/请求数×100
            "display_rate": calc_display,                                # 展示率 = 展示数/匹配数×100
            "click_rate": calc_click,                                    # 点击率 = 点击数/展示数×100
            # --- Pomiad 上游原始比率（仅供参考，与平台公式可能略有差异）---
            "_pomiad_match_rate": row.get("match_rate"),                 # 上游 Match Rate(%)
            "_pomiad_fill_rate": row.get("fill_rate"),                   # 上游 Fill Rate(%)
            "_pomiad_ctr": row.get("ctr"),                               # 上游 CTR(%)，算法可能与 click_rate 不同
        }))
    print_section(f"字段映射预览（全部 {len(mappings)} 条 → 平台字段）")
    print("说明: coverage_rate / display_rate / click_rate 由平台根据数量自动计算，无需 API 映射")
    print("      _pomiad_* 为上游原始比率字段，仅作对照参考，不入库")
    print(dumps_json(mappings))


def print_request_summary() -> None:
    print_section(f"HTTP 交互汇总（共 {len(REQUEST_LOGS)} 次）")
    summary = []
    for log in REQUEST_LOGS:
        summary.append({
            "序号": log["index"],
            "名称": log["name"],
            "时间": log["timestamp"],
            "方法": log["method"],
            "URL": log["url"],
            "耗时_ms": log["elapsed_ms"],
            "HTTP状态": log["status_code"],
            "业务rtn": (log["response_body"] or {}).get("rtn")
            if isinstance(log["response_body"], dict)
            else None,
            "Query参数": log.get("query_params"),
            "Body参数": log.get("request_body"),
        })
    print(dumps_raw_json(summary))


def collect_detail_tasks(sites: list[dict]) -> list[dict]:
    """
    从 api_data 汇总中提取 data_detail 拉取任务。
    不同 site_url（及不同日期）各需单独请求一次。
    """
    tasks: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for site_row in sites:
        site_url = site_row.get("site") or site_row.get("domain_name", "")
        data_date = site_row.get("data_date", "")
        if not site_url or not data_date:
            continue

        key = (site_url, data_date)
        if key in seen:
            continue
        seen.add(key)
        tasks.append({
            "site_url": site_url,
            "data_date": data_date,
            "is_by_country": IS_BY_COUNTRY,
        })

    return tasks


def fetch_all_data_details(token: str, tasks: list[dict]) -> list[dict]:
    """按 site_url + data_date 循环拉取全部明细"""
    all_rows: list[dict] = []
    unique_sites = sorted({t["site_url"] for t in tasks})

    print_section("data_detail 循环拉取计划")
    print(f"不同 site_url 数量: {len(unique_sites)}")
    for site in unique_sites:
        dates = [t["data_date"] for t in tasks if t["site_url"] == site]
        print(f"  - {site}: {len(dates)} 个日期 {dates}")
    print(f"合计请求次数: {len(tasks)}（每个 site_url × 日期 各请求 1 次）")

    for i, task in enumerate(tasks, 1):
        site_url = task["site_url"]
        data_date = task["data_date"]
        print(f"\n>>> 循环 [{i}/{len(tasks)}] site_url={site_url}, data_date={data_date}")

        detail_body = fetch_data_detail(
            token,
            site_url=site_url,
            data_date=data_date,
            is_by_country=task["is_by_country"],
        )
        rtn = detail_body.get("rtn")
        if rtn != 200:
            print(f"  [警告] rtn={rtn}, msg={detail_body.get('msg')}")
            continue

        rows = (detail_body.get("data") or {}).get("data") or []
        all_rows.extend(rows)
        print(f"  => 本站点本日 {len(rows)} 条，累计 {len(all_rows)} 条")

    return all_rows


def find_sites_with_data(token: str) -> tuple[list[dict], str]:
    start_at = TEST_DATES[0]
    end_at = TEST_DATES[-1]
    sites = fetch_api_data_all(token, start_at=start_at, end_at=end_at)
    allowed = set(TEST_DATES)
    sites = [row for row in sites if row.get("data_date") in allowed]
    return sites, ", ".join(TEST_DATES)


def main():
    print_config()
    print("\n流程: login → api_data 获取 site_url 列表 → 按每个 site_url×日期 循环拉 data_detail")

    token = login()

    sites, date_hint = find_sites_with_data(token)
    print_section(f"api_data 数据合计: {len(sites)} 条 ({date_hint})")

    if not sites:
        print("\n[OK] 接口连通正常，账号当前无 api_data 业务数据")
        print_request_summary()
        return

    print_full_table("api_data 全部数据", sites)
    print_all_records_json("api_data", sites, raw=True)
    print_all_records_json("api_data", sites, raw=False)

    detail_tasks = collect_detail_tasks(sites)
    all_detail_rows = fetch_all_data_details(token, detail_tasks)

    print_section(f"data_detail 数据合计: {len(all_detail_rows)} 条明细")
    print_all_records_json("data_detail", all_detail_rows, raw=True)
    print_full_table("data_detail 全部数据（含广告单元）", all_detail_rows)
    print_all_records_json("data_detail", all_detail_rows, raw=False)
    if all_detail_rows:
        print_field_mapping_all(all_detail_rows)

    print_request_summary()
    print("\n[OK] Pomiad API 测试通过（登录 + api_data + data_detail）")


if __name__ == "__main__":
    main()
