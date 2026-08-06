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
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from app.scheduler_module.upstream_http import get_json, post_form, post_json, raise_unless_api_success

UPSTREAM_PAGINATION_MAX_PAGES = 500

ZHISUO_UNIT_PATH = "/api/channelunit"
ZHISUO_COUNTRY_PATH = "/api/channelcountry"
ZHISUO_DAILY_PATH = "/api/channeldaily"
ZHISUO_DATA_PATH = "/api/channeldata"  # 国家+广告单元交叉


@dataclass
class UpstreamFetchStats:
    """上游 API 拉数分页统计，用于任务结果与 Telegram 通知。"""

    pages_fetched: int = 0
    total_pages: int = 0
    rows_fetched: int = 0
    total_rows: int = 0

    @classmethod
    def merge(cls, *items: UpstreamFetchStats) -> UpstreamFetchStats:
        """合并多次拉数（多账号、多日等）的统计。"""
        if not items:
            return cls()
        total_pages = sum(s.total_pages for s in items if s.total_pages > 0)
        total_rows = sum(s.total_rows for s in items if s.total_rows > 0)
        return cls(
            pages_fetched=sum(s.pages_fetched for s in items),
            total_pages=total_pages,
            rows_fetched=sum(s.rows_fetched for s in items),
            total_rows=total_rows,
        )


@dataclass
class UpstreamFetchResult:
    """上游拉数结果：行数据 + 分页统计。"""

    rows: List[Any]
    stats: UpstreamFetchStats = field(default_factory=UpstreamFetchStats)

    @classmethod
    def from_rows(
        cls,
        rows: List[Any],
        *,
        stats: Optional[UpstreamFetchStats] = None,
    ) -> UpstreamFetchResult:
        """无分页接口：单页返回全部数据。"""
        data = rows or []
        if stats is None:
            stats = UpstreamFetchStats(
                pages_fetched=1 if data else 0,
                total_pages=1 if data else 0,
                rows_fetched=len(data),
                total_rows=len(data),
            )
        return cls(rows=data, stats=stats)


def _build_fetch_stats(
    *,
    pages_fetched: int,
    total_pages: int,
    rows_fetched: int,
    total_rows: int,
    limit: int,
) -> UpstreamFetchStats:
    """根据最后一页响应与累计行数生成分页统计。"""
    resolved_total_pages = total_pages
    if resolved_total_pages <= 0 and total_rows > 0 and limit > 0:
        resolved_total_pages = math.ceil(total_rows / limit)
    resolved_total_rows = total_rows if total_rows > 0 else rows_fetched
    return UpstreamFetchStats(
        pages_fetched=pages_fetched,
        total_pages=resolved_total_pages,
        rows_fetched=rows_fetched,
        total_rows=resolved_total_rows,
    )


def unwrap_upstream_fetch_result(
    result: Union[UpstreamFetchResult, List[Any]],
) -> tuple[List[Any], Optional[UpstreamFetchStats]]:
    """兼容拉数函数返回列表或 UpstreamFetchResult。"""
    if isinstance(result, UpstreamFetchResult):
        return result.rows, result.stats
    rows = result or []
    return rows, None


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
) -> UpstreamFetchResult:
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
    rows = json_data.get("data") or []
    return UpstreamFetchResult.from_rows(rows if isinstance(rows, list) else [])


async def fetch_skymobi_rows(
    *,
    api_id: str,
    api_key: str,
    date_str: str,
    limit: int = 1000,
) -> UpstreamFetchResult:
    """Skymobi 按单日拉取 H5 广告数据，全量分页合并 list。"""
    all_rows: List[Any] = []
    page = 1
    last_total = 0
    last_total_pages = 0

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
        last_total = total or last_total
        last_total_pages = total_pages or last_total_pages
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

    stats = _build_fetch_stats(
        pages_fetched=page,
        total_pages=last_total_pages,
        rows_fetched=len(all_rows),
        total_rows=last_total,
        limit=limit,
    )
    return UpstreamFetchResult(rows=all_rows, stats=stats)


async def fetch_tqt_rows(
    *,
    url: str,
    params: Dict[str, Any],
    headers: Dict[str, str],
    api_secret: Optional[str] = None,
) -> UpstreamFetchResult:
    """
    TQT 拉数：兼容 state=ok 或 code=200，从 data.list 或顶层 list 取行。

    当提供 api_secret 时按 page/pageSize 全量分页，每页重新签名。
    """
    all_rows: List[Any] = []
    page = 1
    page_size = int(params.get("pageSize") or 1000)
    last_total = 0
    last_total_pages = 0
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

        last_total = total or last_total
        last_total_pages = total_pages or last_total_pages
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

    stats = _build_fetch_stats(
        pages_fetched=page,
        total_pages=last_total_pages,
        rows_fetched=len(all_rows),
        total_rows=last_total,
        limit=page_size,
    )
    return UpstreamFetchResult(rows=all_rows, stats=stats)


async def fetch_tbsj_rows(
    *,
    base_url: str,
    start: str,
    end: str,
    headers: Dict[str, Any],
    limit: int = 1000,
) -> UpstreamFetchResult:
    """
    TBSJ 国家+广告单元交叉接口（路径名 /adunit，响应含 country_code + ad_unit）。

    上游另有 /unit_data（仅单元）、/country（仅国家）、/data（日汇总），生产不接入。
    按 total 全量分页，成功码 20000。
    """
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
            label=f"TBSJ API adunit/cross (page={page})",
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

    stats = _build_fetch_stats(
        pages_fetched=page,
        total_pages=0,
        rows_fetched=len(all_rows),
        total_rows=total,
        limit=limit,
    )
    return UpstreamFetchResult(rows=all_rows, stats=stats)


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
) -> UpstreamFetchResult:
    """Addermobi POST 拉数，status=0 为成功，全量分页后经 extract_addermobi_rows 解析行。"""
    all_rows: List[Any] = []
    page = 1
    page_size = int(payload.get("rows") or 1000)
    last_total = 0
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
        last_total = total or last_total
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

    stats = _build_fetch_stats(
        pages_fetched=page,
        total_pages=0,
        rows_fetched=len(all_rows),
        total_rows=last_total,
        limit=page_size,
    )
    return UpstreamFetchResult(rows=all_rows, stats=stats)


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
    per_day: bool = True,
) -> UpstreamFetchResult:
    """
    拉取 zhisuo 报表接口（分页合并 list）。

    per_day=True 时按自然日循环请求，避免多天区间查询只返回前 N 条导致漏数。
    """
    if per_day and start != end:
        from datetime import date, timedelta

        all_rows: List[Any] = []
        stats_list: list[UpstreamFetchStats] = []
        current = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        while current <= end_date:
            day = current.isoformat()
            day_result = await fetch_zhisuo_report_rows(
                base_url=base_url,
                client_id=client_id,
                api_key=api_key,
                start=day,
                end=day,
                path=path,
                label=label,
                limit=limit,
                per_day=False,
            )
            all_rows.extend(day_result.rows)
            stats_list.append(day_result.stats)
            current += timedelta(days=1)
        return UpstreamFetchResult(
            rows=all_rows,
            stats=UpstreamFetchStats.merge(*stats_list) if stats_list else UpstreamFetchStats(),
        )

    base = base_url.rstrip("/")
    all_rows: List[Any] = []
    page = 1
    last_total = 0
    last_total_pages = 0

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
        last_total = total or last_total
        last_total_pages = total_pages or last_total_pages
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

    stats = _build_fetch_stats(
        pages_fetched=page,
        total_pages=last_total_pages,
        rows_fetched=len(all_rows),
        total_rows=last_total,
        limit=limit,
    )
    return UpstreamFetchResult(rows=all_rows, stats=stats)


async def fetch_zhisuo_unit_rows(
    *,
    base_url: str,
    client_id: str,
    api_key: str,
    start: str,
    end: str,
    limit: int = 1000,
) -> UpstreamFetchResult:
    """拉取 zhisuo 广告单元报告（按天循环 + 分页）。"""
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
) -> UpstreamFetchResult:
    """拉取 zhisuo 国家报告（按天循环 + 分页）。"""
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


async def fetch_zhisuo_daily_rows(
    *,
    base_url: str,
    client_id: str,
    api_key: str,
    start: str,
    end: str,
    limit: int = 1000,
) -> UpstreamFetchResult:
    """拉取 zhisuo 日报（channeldaily，按天循环 + 分页）。"""
    return await fetch_zhisuo_report_rows(
        base_url=base_url,
        client_id=client_id,
        api_key=api_key,
        start=start,
        end=end,
        path=ZHISUO_DAILY_PATH,
        label="Zhisuo 日报 API",
        limit=limit,
    )


async def fetch_zhisuo_data_rows(
    *,
    base_url: str,
    client_id: str,
    api_key: str,
    start: str,
    end: str,
    limit: int = 1000,
) -> UpstreamFetchResult:
    """拉取 zhisuo 国家+广告单元交叉报告（channeldata，按天循环 + 分页）。"""
    return await fetch_zhisuo_report_rows(
        base_url=base_url,
        client_id=client_id,
        api_key=api_key,
        start=start,
        end=end,
        path=ZHISUO_DATA_PATH,
        label="Zhisuo 国家+广告单元 API",
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
) -> UpstreamFetchResult:
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
    last_api_total = 0

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
        last_api_total = total or last_api_total
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
        return UpstreamFetchResult(rows=[], stats=UpstreamFetchStats())

    api_stats = _build_fetch_stats(
        pages_fetched=page,
        total_pages=0,
        rows_fetched=scanned_rows,
        total_rows=last_api_total,
        limit=api_data_limit,
    )

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

    detail_stats = UpstreamFetchStats(
        pages_fetched=api_stats.pages_fetched,
        total_pages=api_stats.total_pages,
        rows_fetched=len(all_detail_rows),
        total_rows=last_api_total or len(all_detail_rows),
    )
    return UpstreamFetchResult(rows=all_detail_rows, stats=detail_stats)


# H5 Deer 开放 API（参见 tests/API/H5 deer Api对接文档-新版.pdf）
H5DEER_TOKEN_PATH = "/api/user_oauth/token"
H5DEER_REPORT_PATH = "/v1/api/h5report"
# 默认最细颗粒度；dimension 参数拼写为 ad_nuit，响应字段为 adNuit
H5DEER_DEFAULT_DIMENSION = "date,url,country_code,ad_nuit"


def _h5deer_ok(json_data: Dict[str, Any]) -> bool:
    """H5 Deer 业务成功判断：code == 200。"""
    return json_data.get("code") == 200


async def _h5deer_login(*, base_url: str, username: str, password: str) -> str:
    """H5 Deer 登录获取 JWT access token（Header 形如 ``JWT <token>``）。"""
    url = f"{base_url.rstrip('/')}{H5DEER_TOKEN_PATH}"
    json_data = await post_json(
        url,
        json_body={"username": username, "password": password},
        headers={"Content-Type": "application/json"},
        label="H5 Deer API 登录",
    )
    raise_unless_api_success(json_data, _h5deer_ok, label="H5 Deer API 登录")
    token = json_data.get("token")
    if not token:
        raise Exception("H5 Deer API 登录成功但未返回 token")
    return str(token)


async def fetch_h5deer_rows(
    *,
    base_url: str,
    username: str,
    password: str,
    start: str,
    end: str,
    dimension: str = H5DEER_DEFAULT_DIMENSION,
    limit: int = 500,
) -> UpstreamFetchResult:
    """
    H5 Deer 拉数：先 POST token，再分页 GET h5report。

    Authorization 必须为 ``JWT <token>``（文档约定，非 Bearer）。
    limit 上限 500；dimension 默认 date,url,country_code,ad_nuit（最细颗粒度）。
    """
    base = base_url.rstrip("/")
    page_size = max(1, min(int(limit or 500), 500))
    dims = (dimension or H5DEER_DEFAULT_DIMENSION).strip() or H5DEER_DEFAULT_DIMENSION
    token = await _h5deer_login(base_url=base, username=username, password=password)
    auth_headers = {"Authorization": f"JWT {token}"}

    all_rows: List[Any] = []
    page = 1
    last_total = 0
    report_url = f"{base}{H5DEER_REPORT_PATH}"

    while True:
        params = {
            "page": page,
            "limit": page_size,
            "start_date": start,
            "end_date": end,
            "dimension": dims,
        }
        json_data = await get_json(
            report_url,
            params=params,
            headers=auth_headers,
            label=f"H5 Deer h5report (page={page})",
        )
        # token 过期时重新登录并重试当前页一次
        if json_data.get("code") in (401, 403) or "token" in str(json_data.get("msg") or "").lower():
            token = await _h5deer_login(base_url=base, username=username, password=password)
            auth_headers = {"Authorization": f"JWT {token}"}
            json_data = await get_json(
                report_url,
                params=params,
                headers=auth_headers,
                label=f"H5 Deer h5report (page={page}, reauth)",
            )
        raise_unless_api_success(json_data, _h5deer_ok, label="H5 Deer h5report")

        rows = json_data.get("data") or []
        if not isinstance(rows, list):
            rows = []
        all_rows.extend(rows)

        total = int(json_data.get("totalcount") or 0)
        last_total = total or last_total
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

    stats = _build_fetch_stats(
        pages_fetched=page,
        total_pages=0,
        rows_fetched=len(all_rows),
        total_rows=last_total,
        limit=page_size,
    )
    return UpstreamFetchResult(rows=all_rows, stats=stats)


# Aya / AB Data 开放 API（参见 tests/API/ab_data_API文档(1).pdf）
AYA_PATH_DAILY = "/api/advertData/getDay"
AYA_PATH_COUNTRY = "/api/advertData/getAdsDataCountry"
AYA_PATH_UNIT = "/api/advertData/getAdsDataUnit"


async def fetch_aya_rows(
    *,
    base_url: str,
    secret_key: str,
    start: str,
    end: str,
    path: str,
    label: str = "Aya API",
) -> UpstreamFetchResult:
    """
    Aya 拉数：POST application/x-www-form-urlencoded，成功码 code=200，行在 data 数组。

    文档虽写 post，但服务端要求 form 参数而非 JSON Body。
    """
    url = f"{base_url.rstrip('/')}{path}"
    json_data = await post_form(
        url,
        form_body={
            "secretKey": secret_key,
            "startDate": start,
            "endDate": end,
        },
        label=label,
    )
    raise_unless_api_success(json_data, {200}, label=label, code_key="code")
    rows = json_data.get("data") or []
    if not isinstance(rows, list):
        rows = []
    return UpstreamFetchResult.from_rows(rows)


# FlyMobi 广告系统 API（ads.gofinds.xyz）
# 文档：countryList / adUnitList / dayList，Bearer Token 鉴权，30次/小时限速

async def fetch_flymobi_rows(
    *,
    base_url: str,
    token: str,
    start: str,
    end: str,
    path: str,
    label: str = "FlyMobi API",
    limit: int = 500,
) -> UpstreamFetchResult:
    """
    FlyMobi 拉数：POST JSON + Bearer Token 鉴权，按 total 全量分页。

    响应 code==200 成功，code==201 暂无数据（视为空），其余抛异常。
    """
    url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    all_rows: List[Any] = []
    page = 1
    last_total = 0

    while True:
        json_data = await post_json(
            url,
            json_body={
                "startDate": start,
                "endDate": end,
                "pageSize": limit,
                "pageNum": page,
            },
            headers=headers,
            label=f"{label} (page={page})",
        )
        code = json_data.get("code")
        if code == 201:
            break
        raise_unless_api_success(json_data, {200}, label=label, code_key="code")

        rows = json_data.get("data") or []
        if not isinstance(rows, list):
            rows = []
        all_rows.extend(rows)

        total = int(json_data.get("total") or 0)
        last_total = total or last_total
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

    stats = _build_fetch_stats(
        pages_fetched=page,
        total_pages=0,
        rows_fetched=len(all_rows),
        total_rows=last_total,
        limit=limit,
    )
    return UpstreamFetchResult(rows=all_rows, stats=stats)
