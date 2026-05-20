"""
各上游 API 拉数封装（HTTP + 成功判断 + 数据列表提取）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.scheduler_module.upstream_http import post_json, raise_unless_api_success


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
