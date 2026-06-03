"""
各上游 API 拉数封装（HTTP + 成功判断 + 数据列表提取）。
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from app.scheduler_module.upstream_http import get_json, post_json, raise_unless_api_success

ZHISUO_UNIT_PATH = "/api/channelunit"


def build_zhisuo_sign(params: Dict[str, Any]) -> str:
    """按参数名 ASCII 排序后拼接并 MD5（小写）。"""
    sorted_params = sorted(params.items())
    query = "&".join(f"{k}={v}" for k, v in sorted_params)
    return hashlib.md5(query.encode("utf-8")).hexdigest()


async def fetch_huguang_rows(
    *,
    domain: str,
    api_key: str,
    username: str,
    start: str,
    end: str,
) -> List[Any]:
    url = f"http://{domain}:5858/api/country"
    json_data = await post_json(
        url,
        json_body={
            "key": api_key,
            "startdate": start,
            "enddate": end,
            "username": username,
        },
        label="Huguang API",
        verify=False,
    )
    raise_unless_api_success(json_data, {0}, label="Huguang API", code_key="code")
    return json_data.get("data") or []


async def fetch_skymobi_rows(
    *,
    api_id: str,
    api_key: str,
    date_str: str,
) -> List[Any]:
    url = (
        f"https://crm.skymobi.online/api/adxh5"
        f"?apikey={api_key}&date={date_str}&uid={api_id}&page=1&limit=1000"
    )
    json_data = await post_json(url, label="Skymobi API")
    raise_unless_api_success(json_data, {0}, label="Skymobi API", code_key="ret")
    return json_data.get("list") or []


async def fetch_tqt_rows(
    *,
    url: str,
    params: Dict[str, Any],
    headers: Dict[str, str],
) -> List[Any]:
    json_data = await post_json(url, json_body=params, headers=headers, label="TQT API")

    def _ok(data: Dict[str, Any]) -> bool:
        return data.get("state") == "ok" or data.get("code") == 200

    raise_unless_api_success(json_data, _ok, label="TQT API")
    if "data" in json_data and isinstance(json_data["data"], dict):
        return json_data["data"].get("list") or []
    return json_data.get("list") or []


async def fetch_tbsj_rows(
    *,
    base_url: str,
    params: Dict[str, Any],
    headers: Dict[str, str],
) -> List[Any]:
    json_data = await post_json(
        base_url + "/adunit",
        json_body=params,
        headers=headers,
        label="TBSJ API",
        verify=False,
    )
    raise_unless_api_success(json_data, {20000}, label="TBSJ API", code_key="code")
    if "data" in json_data and isinstance(json_data["data"], dict):
        return json_data["data"].get("items") or []
    return json_data.get("items") or []


def extract_addermobi_rows(json_data: Dict[str, Any]) -> List[Any]:
    if "rows" in json_data:
        rows_value = json_data["rows"]
        if isinstance(rows_value, list):
            return rows_value
        if isinstance(rows_value, dict):
            return (
                rows_value.get("list")
                or rows_value.get("items")
                or rows_value.get("data")
                or []
            )
    return json_data.get("data") or json_data.get("list") or []


async def fetch_addermobi_rows(
    *,
    url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
) -> List[Any]:
    json_data = await post_json(url, json_body=payload, headers=headers, label="Addermobi API")
    raise_unless_api_success(json_data, {0}, label="Addermobi API", code_key="status")
    return extract_addermobi_rows(json_data)


async def fetch_zhisuo_unit_rows(
    *,
    base_url: str,
    client_id: str,
    api_key: str,
    start: str,
    end: str,
    limit: int = 100,
) -> List[Any]:
    """拉取 zhisuo 广告单元报告（分页合并 list）。"""
    base = base_url.rstrip("/")
    all_rows: List[Any] = []
    page = 1

    while True:
        timestamp = int(time.time() * 1000)
        sign_params: Dict[str, Any] = {
            "clientId": client_id,
            "start_date": start,
            "end_date": end,
            "timestamp": timestamp,
            "limit": limit,
            "page": page,
            "key": api_key,
        }
        sign = build_zhisuo_sign(sign_params)
        request_params = {k: v for k, v in sign_params.items() if k != "key"}
        request_params["sign"] = sign

        json_data = await get_json(
            base + ZHISUO_UNIT_PATH,
            params=request_params,
            label="Zhisuo API",
        )
        raise_unless_api_success(json_data, {1}, label="Zhisuo API", code_key="code")

        data_block = json_data.get("data") or {}
        if not isinstance(data_block, dict):
            break

        rows = data_block.get("list") or []
        if isinstance(rows, list):
            all_rows.extend(rows)

        total_pages = int(data_block.get("total_pages") or 1)
        if page >= total_pages:
            break
        page += 1

    return all_rows


def _pomiad_ok(json_data: Dict[str, Any]) -> bool:
    return json_data.get("rtn") == 200


async def _pomiad_login(
    *,
    base_url: str,
    username: str,
    password: str,
) -> str:
    url = f"{base_url.rstrip('/')}/login"
    json_data = await post_json(
        url,
        json_body={"username": username, "password": password},
        label="Pomiad API 登录",
    )
    raise_unless_api_success(json_data, _pomiad_ok, label="Pomiad API 登录")
    token = json_data.get("token")
    if not token:
        raise Exception("Pomiad API 登录成功但未返回 token")
    return str(token)


async def fetch_pomiad_rows(
    *,
    base_url: str,
    username: str,
    password: str,
    start: str,
    end: str,
    is_by_country: int = 0,
    api_data_limit: int = 100,
) -> List[Any]:
    """
    Pomiad 拉数：login → api_data 发现站点 → 按 site_url×日期循环 data_detail。
    返回 data_detail 明细列表（入库数据源）。
    """
    base = base_url.rstrip("/")
    api_data_url = f"{base}/normal/api_data"
    data_detail_url = f"{base}/normal/data_detail"

    token = await _pomiad_login(base_url=base, username=username, password=password)
    auth_headers = {"Authorization": token}

    site_tasks: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    page = 1

    while True:
        params = {
            "page": page,
            "limit": api_data_limit,
            "start_at": start,
            "end_at": end,
        }
        json_data = await get_json(
            api_data_url,
            params=params,
            headers=auth_headers,
            label="Pomiad api_data",
        )
        if json_data.get("rtn") == 401:
            token = await _pomiad_login(base_url=base, username=username, password=password)
            auth_headers = {"Authorization": token}
            json_data = await get_json(
                api_data_url,
                params=params,
                headers=auth_headers,
                label="Pomiad api_data",
            )
        raise_unless_api_success(json_data, _pomiad_ok, label="Pomiad api_data")

        wrapper = json_data.get("data") or {}
        rows = wrapper.get("data") or []
        for row in rows:
            site_url = row.get("site") or row.get("domain_name") or ""
            data_date = row.get("data_date") or ""
            if not site_url or not data_date:
                continue
            key = (site_url, data_date)
            if key not in seen:
                seen.add(key)
                site_tasks.append(key)

        total = int(wrapper.get("count") or 0)
        if page * api_data_limit >= total or not rows:
            break
        page += 1

    if not site_tasks:
        return []

    all_detail_rows: List[Any] = []
    for site_url, data_date in site_tasks:
        payload = {
            "site_url": site_url,
            "data_date": data_date,
            "is_by_country": is_by_country,
        }
        json_data = await post_json(
            data_detail_url,
            json_body=payload,
            headers={**auth_headers, "Content-Type": "application/json"},
            label=f"Pomiad data_detail ({site_url} @ {data_date})",
        )
        if json_data.get("rtn") == 401:
            token = await _pomiad_login(base_url=base, username=username, password=password)
            auth_headers = {"Authorization": token}
            json_data = await post_json(
                data_detail_url,
                json_body=payload,
                headers={**auth_headers, "Content-Type": "application/json"},
                label=f"Pomiad data_detail ({site_url} @ {data_date})",
            )
        raise_unless_api_success(
            json_data,
            _pomiad_ok,
            label=f"Pomiad data_detail ({site_url} @ {data_date})",
        )
        detail_rows = (json_data.get("data") or {}).get("data") or []
        if isinstance(detail_rows, list):
            all_detail_rows.extend(detail_rows)

    return all_detail_rows


def _pomiad_ok(json_data: Dict[str, Any]) -> bool:
    return json_data.get("rtn") == 200


async def _pomiad_login(
    *,
    base_url: str,
    username: str,
    password: str,
) -> str:
    url = f"{base_url.rstrip('/')}/login"
    json_data = await post_json(
        url,
        json_body={"username": username, "password": password},
        label="Pomiad API 登录",
    )
    raise_unless_api_success(json_data, _pomiad_ok, label="Pomiad API 登录")
    token = json_data.get("token")
    if not token:
        raise Exception("Pomiad API 登录成功但未返回 token")
    return str(token)


async def fetch_pomiad_rows(
    *,
    base_url: str,
    username: str,
    password: str,
    start: str,
    end: str,
    is_by_country: int = 0,
    api_data_limit: int = 100,
) -> List[Any]:
    """
    Pomiad 拉数：login → api_data 发现站点 → 按 site_url×日期循环 data_detail。
    返回 data_detail 明细列表（入库数据源）。
    """
    base = base_url.rstrip("/")
    api_data_url = f"{base}/normal/api_data"
    data_detail_url = f"{base}/normal/data_detail"

    token = await _pomiad_login(base_url=base, username=username, password=password)
    auth_headers = {"Authorization": token}

    # 1. api_data 分页获取站点任务
    site_tasks: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    page = 1

    while True:
        params = {
            "page": page,
            "limit": api_data_limit,
            "start_at": start,
            "end_at": end,
        }
        json_data = await get_json(
            api_data_url,
            params=params,
            headers=auth_headers,
            label="Pomiad api_data",
        )
        if json_data.get("rtn") == 401:
            token = await _pomiad_login(base_url=base, username=username, password=password)
            auth_headers = {"Authorization": token}
            json_data = await get_json(
                api_data_url,
                params=params,
                headers=auth_headers,
                label="Pomiad api_data",
            )
        raise_unless_api_success(json_data, _pomiad_ok, label="Pomiad api_data")

        wrapper = json_data.get("data") or {}
        rows = wrapper.get("data") or []
        for row in rows:
            site_url = row.get("site") or row.get("domain_name") or ""
            data_date = row.get("data_date") or ""
            if not site_url or not data_date:
                continue
            key = (site_url, data_date)
            if key not in seen:
                seen.add(key)
                site_tasks.append(key)

        total = int(wrapper.get("count") or 0)
        if page * api_data_limit >= total or not rows:
            break
        page += 1

    if not site_tasks:
        return []

    # 2. 循环 data_detail
    all_detail_rows: List[Any] = []
    for site_url, data_date in site_tasks:
        payload = {
            "site_url": site_url,
            "data_date": data_date,
            "is_by_country": is_by_country,
        }
        json_data = await post_json(
            data_detail_url,
            json_body=payload,
            headers={**auth_headers, "Content-Type": "application/json"},
            label=f"Pomiad data_detail ({site_url} @ {data_date})",
        )
        if json_data.get("rtn") == 401:
            token = await _pomiad_login(base_url=base, username=username, password=password)
            auth_headers = {"Authorization": token}
            json_data = await post_json(
                data_detail_url,
                json_body=payload,
                headers={**auth_headers, "Content-Type": "application/json"},
                label=f"Pomiad data_detail ({site_url} @ {data_date})",
            )
        raise_unless_api_success(
            json_data,
            _pomiad_ok,
            label=f"Pomiad data_detail ({site_url} @ {data_date})",
        )
        detail_rows = (json_data.get("data") or {}).get("data") or []
        if isinstance(detail_rows, list):
            all_detail_rows.extend(detail_rows)

    return all_detail_rows
