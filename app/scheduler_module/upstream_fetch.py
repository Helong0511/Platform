"""
各上游广告主 API 拉数封装模块。

功能说明：
- 为每家上游提供 ``fetch_*_rows``：鉴权、分页、业务成功码校验、行列表提取
- 统一通过 ``upstream_http`` 发起 HTTP，减少各 task 重复 httpx 代码

在系统中的位置：
- 被 skymobi/tqt/huguang 等各上游定时任务调用

注意事项：
1. 字段路径变更须同步更新 upstream_import 的列映射
2. 拉数失败应抛明确异常，由 task 层捕获并 set_task_result
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from app.scheduler_module.upstream_http import get_json, post_json, raise_unless_api_success

UPSTREAM_PAGINATION_MAX_PAGES = 500

ZHISUO_UNIT_PATH = "/api/channelunit"
ZHISUO_COUNTRY_PATH = "/api/channelcountry"


def build_zhisuo_sign(params: Dict[str, Any]) -> str:
    """按参数名 ASCII 排序后拼接并 MD5（小写）。"""
    sorted_params = sorted(params.items())
    query = "&".join(f"{k}={v}" for k, v in sorted_params)
    return hashlib.md5(query.encode("utf-8")).hexdigest()


def build_tqt_sign(params: Dict[str, Any], api_secret: str) -> str:
    """TQT 报表接口 MD5 签名（与 tqt_task.generate_sign 规则一致）。"""
    sorted_items = sorted((k, v) for k, v in params.items() if k != "sign")
    query_str = "".join(f"{k}{v}" for k, v in sorted_items)
    full_str = f"{api_secret}{query_str}{api_secret}".lower()
    return hashlib.md5(full_str.encode("utf-8")).hexdigest().lower()


def _should_break_upstream_pagination(
    rows: Any,
    *,
    total: int,
    collected: int,
    page: int,
    total_pages: int,
    limit: int,
    max_pages: int = UPSTREAM_PAGINATION_MAX_PAGES,
) -> bool:
    """
    上游 API 分页终止判断（通用）。

    - 空页立即停止
    - 累计达到 total 时停止
    - 存在 total_pages 时以其为主；已到声明末页但累计未达 total 则继续翻页
    - 无 total_pages 时依据 total 与本页是否满 limit 判断
    - 超过 max_pages 强制停止，防止死循环
    """
    if page > max_pages:
        return True
    if not isinstance(rows, list) or not rows:
        return True
    if total > 0 and collected >= total:
        return True
    if total_pages > 0:
        if page < total_pages:
            return False
        if total > 0 and collected < total:
            return False
        return len(rows) < limit
    if total > 0:
        return False
    return len(rows) < limit


async def fetch_huguang_rows(
    *,
    domain: str,
    api_key: str,
    username: str,
    start: str,
    end: str,
) -> List[Any]:
    """Huguang 按国家维度拉取广告数据，返回 data 列表。"""
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
    limit: int = 1000,
) -> List[Any]:
    """Skymobi 按单日拉取 H5 广告数据，全量分页合并 list。"""
    all_rows: List[Any] = []
    page = 1

    while True:
        url = (
            f"https://crm.skymobi.online/api/adxh5"
            f"?apikey={api_key}&date={date_str}&uid={api_id}&page={page}&limit={limit}"
        )
        json_data = await post_json(url, label=f"Skymobi API (page={page})")
        raise_unless_api_success(json_data, {0}, label="Skymobi API", code_key="ret")

        rows = json_data.get("list") or []
        if isinstance(rows, list):
            all_rows.extend(rows)

        total = int(json_data.get("total") or json_data.get("totalRow") or 0)
        total_pages = int(
            json_data.get("totalPage") or json_data.get("total_pages") or 0
        )
        if _should_break_upstream_pagination(
            rows,
            total=total,
            collected=len(all_rows),
            page=page,
            total_pages=total_pages,
            limit=limit,
        ):
            break
        page += 1

    return all_rows


async def fetch_tqt_rows(
    *,
    url: str,
    params: Dict[str, Any],
    headers: Dict[str, str],
    api_secret: Optional[str] = None,
) -> List[Any]:
    """
    TQT 拉数：兼容 state=ok 或 code=200，从 data.list 或顶层 list 取行。

    当提供 api_secret 时按 page/pageSize 全量分页，每页重新签名。
    """
    all_rows: List[Any] = []
    page = 1
    page_size = int(params.get("pageSize") or 1000)
    base_params = {
        k: v for k, v in params.items() if k not in ("page", "pageSize", "sign")
    }

    while True:
        request_params = {**base_params, "page": page, "pageSize": page_size}
        if api_secret:
            request_params["sign"] = build_tqt_sign(request_params, api_secret)
        elif page == 1 and "sign" in params:
            request_params["sign"] = params["sign"]
        else:
            raise ValueError("TQT 分页拉数需提供 api_secret 以按页重签")

        json_data = await post_json(
            url,
            json_body=request_params,
            headers=headers,
            label=f"TQT API (page={page})",
        )

        def _ok(data: Dict[str, Any]) -> bool:
            return data.get("state") == "ok" or data.get("code") == 200

        raise_unless_api_success(json_data, _ok, label="TQT API")

        if "data" in json_data and isinstance(json_data["data"], dict):
            block = json_data["data"]
            rows = block.get("list") or []
            total = int(block.get("totalRow") or 0)
            total_pages = int(block.get("totalPage") or 0)
        else:
            block = {}
            rows = json_data.get("list") or []
            total = int(json_data.get("totalRow") or 0)
            total_pages = int(json_data.get("totalPage") or 0)

        if isinstance(rows, list):
            all_rows.extend(rows)

        if _should_break_upstream_pagination(
            rows,
            total=total,
            collected=len(all_rows),
            page=page,
            total_pages=total_pages,
            limit=page_size,
        ):
            break
        page += 1

    return all_rows


async def fetch_tbsj_rows(
    *,
    base_url: str,
    start: str,
    end: str,
    headers: Dict[str, Any],
    limit: int = 1000,
) -> List[Any]:
    """TBSJ 广告单元接口（/adunit），按 total 全量分页，成功码 20000。"""
    base = base_url.rstrip("/")
    start_at, end_at = format_tbsj_datetime_range(start, end)
    all_rows: List[Any] = []
    page = 1
    total = 0

    while True:
        json_data = await post_json(
            base + "/adunit",
            json_body={
                "page": page,
                "limit": limit,
                "start": start_at,
                "end": end_at,
            },
            headers=headers,
            label=f"TBSJ API adunit (page={page})",
            verify=False,
        )
        raise_unless_api_success(json_data, {20000}, label="TBSJ API", code_key="code")

        data_block = json_data.get("data") or {}
        if not isinstance(data_block, dict):
            break

        rows = data_block.get("items") or []
        if isinstance(rows, list):
            all_rows.extend(rows)

        total = int(data_block.get("total") or total)
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

    return all_rows


def format_tbsj_datetime_range(start: str, end: str) -> tuple[str, str]:
    """TBSJ API 日期范围：start 日 00:00:00，end 日 23:59:59。"""
    start_day = (start or "").strip()[:10]
    end_day = (end or start or "").strip()[:10]
    return f"{start_day} 00:00:00", f"{end_day} 23:59:59"


def extract_addermobi_rows(json_data: Dict[str, Any]) -> List[Any]:
    """Addermobi 响应行提取：兼容 rows 为 list/dict 及 data/list 多种嵌套。"""
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
    """Addermobi POST 拉数，status=0 为成功，全量分页后经 extract_addermobi_rows 解析行。"""
    all_rows: List[Any] = []
    page = 1
    page_size = int(payload.get("rows") or 1000)
    base_payload = {k: v for k, v in payload.items() if k != "page"}

    while True:
        request_payload = {**base_payload, "page": page}
        json_data = await post_json(
            url,
            json_body=request_payload,
            headers=headers,
            label=f"Addermobi API (page={page})",
        )
        raise_unless_api_success(json_data, {0}, label="Addermobi API", code_key="status")

        rows = extract_addermobi_rows(json_data)
        if not isinstance(rows, list):
            rows = []
        all_rows.extend(rows)

        total = int(json_data.get("total") or 0)
        if _should_break_upstream_pagination(
            rows,
            total=total,
            collected=len(all_rows),
            page=page,
            total_pages=0,
            limit=page_size,
        ):
            break
        page += 1

    return all_rows


async def fetch_zhisuo_report_rows(
    *,
    base_url: str,
    client_id: str,
    api_key: str,
    start: str,
    end: str,
    path: str,
    label: str = "Zhisuo API",
    limit: int = 1000,
) -> List[Any]:
    """拉取 zhisuo 报表接口（分页合并 list）。"""
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
            base + path,
            params=request_params,
            label=label,
        )
        raise_unless_api_success(json_data, {1}, label=label, code_key="code")

        data_block = json_data.get("data") or {}
        if not isinstance(data_block, dict):
            break

        rows = data_block.get("list") or []
        if isinstance(rows, list):
            all_rows.extend(rows)

        total = int(data_block.get("total") or 0)
        total_pages = int(data_block.get("total_pages") or 1)
        if _should_break_upstream_pagination(
            rows,
            total=total,
            collected=len(all_rows),
            page=page,
            total_pages=total_pages,
            limit=limit,
        ):
            break
        page += 1

    return all_rows


async def fetch_zhisuo_unit_rows(
    *,
    base_url: str,
    client_id: str,
    api_key: str,
    start: str,
    end: str,
    limit: int = 1000,
) -> List[Any]:
    """拉取 zhisuo 广告单元报告（分页合并 list）。"""
    return await fetch_zhisuo_report_rows(
        base_url=base_url,
        client_id=client_id,
        api_key=api_key,
        start=start,
        end=end,
        path=ZHISUO_UNIT_PATH,
        label="Zhisuo 广告单元 API",
        limit=limit,
    )


async def fetch_zhisuo_country_rows(
    *,
    base_url: str,
    client_id: str,
    api_key: str,
    start: str,
    end: str,
    limit: int = 1000,
) -> List[Any]:
    """拉取 zhisuo 国家报告（分页合并 list）。"""
    return await fetch_zhisuo_report_rows(
        base_url=base_url,
        client_id=client_id,
        api_key=api_key,
        start=start,
        end=end,
        path=ZHISUO_COUNTRY_PATH,
        label="Zhisuo 国家报告 API",
        limit=limit,
    )


# Pomiad 接口路径（参见 tests/Pomiad_com_data_api.pdf）
POMIAD_API_DATA_PATH = "/normal/api_data"
POMIAD_DATA_DETAIL_PATH = "/normal/data_detail"


def _pomiad_ok(json_data: Dict[str, Any]) -> bool:
    """Pomiad 业务成功判断：rtn == 200。"""
    return json_data.get("rtn") == 200


async def _pomiad_login(
    *,
    base_url: str,
    username: str,
    password: str,
) -> str:
    """Pomiad 登录获取 Authorization token，供后续 api_data / data_detail 使用。"""
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


async def _pomiad_post_with_reauth(
    *,
    url: str,
    payload: Dict[str, Any],
    auth_headers: Dict[str, str],
    base_url: str,
    username: str,
    password: str,
    label: str,
) -> Dict[str, Any]:
    """Pomiad POST 请求；401 时自动重新登录并重试一次。"""
    json_data = await post_json(
        url,
        json_body=payload,
        headers={**auth_headers, "Content-Type": "application/json"},
        label=label,
    )
    if json_data.get("rtn") == 401:
        token = await _pomiad_login(base_url=base_url, username=username, password=password)
        auth_headers["Authorization"] = token
        json_data = await post_json(
            url,
            json_body=payload,
            headers={**auth_headers, "Content-Type": "application/json"},
            label=label,
        )
    return json_data


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
    Pomiad 拉数（参数与流程参见 tests/Pomiad_com_data_api.pdf）。

    阶段一 GET api_data：Query page、limit、start_at、end_at，发现 site + data_date。
    阶段二 POST data_detail：Body site_url、data_date、is_by_country，拉广告单元明细。
    """
    base = base_url.rstrip("/")
    api_data_url = f"{base}{POMIAD_API_DATA_PATH}"
    data_detail_url = f"{base}{POMIAD_DATA_DETAIL_PATH}"

    token = await _pomiad_login(base_url=base, username=username, password=password)
    auth_headers = {"Authorization": token}

    # ---- 阶段一：api_data 分页（GET ?page=&limit=&start_at=&end_at=）----
    site_tasks: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    page = 1
    scanned_rows = 0

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
            label=f"Pomiad api_data (page={page})",
        )
        if json_data.get("rtn") == 401:
            token = await _pomiad_login(base_url=base, username=username, password=password)
            auth_headers = {"Authorization": token}
            json_data = await get_json(
                api_data_url,
                params=params,
                headers=auth_headers,
                label=f"Pomiad api_data (page={page})",
            )
        raise_unless_api_success(json_data, _pomiad_ok, label="Pomiad api_data")

        wrapper = json_data.get("data") or {}
        rows = wrapper.get("data") or []
        if not isinstance(rows, list):
            rows = []
        scanned_rows += len(rows)
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
        if _should_break_upstream_pagination(
            rows,
            total=total,
            collected=scanned_rows,
            page=page,
            total_pages=0,
            limit=api_data_limit,
        ):
            break
        page += 1

    if not site_tasks:
        return []

    # ---- 阶段二：data_detail 按站点×日期拉明细（POST JSON）----
    all_detail_rows: List[Any] = []
    for site_url, data_date in site_tasks:
        payload = {
            "site_url": site_url,
            "data_date": data_date,
            "is_by_country": is_by_country,
        }
        label = f"Pomiad data_detail ({site_url} @ {data_date})"
        json_data = await _pomiad_post_with_reauth(
            url=data_detail_url,
            payload=payload,
            auth_headers=auth_headers,
            base_url=base,
            username=username,
            password=password,
            label=label,
        )
        raise_unless_api_success(json_data, _pomiad_ok, label=label)
        detail_rows = (json_data.get("data") or {}).get("data") or []
        if isinstance(detail_rows, list):
            all_detail_rows.extend(detail_rows)

    return all_detail_rows
