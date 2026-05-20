"""
业务层 click_id 令牌：生成与解析，并与 Postback Click 关联结构兼容。

生产兼容策略：
- ``USE_TRACKING_TOKEN=false``（默认）：生成仍走旧版随机 click_id，与现网一致。
- 解析：始终先尝试令牌解析；失败则回退 ``clicks`` 表查询（旧 click_id 不受影响）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.tracking.ad_tracking_codec import (
    AdTrackingCodec,
    REASON_OK,
    TOKEN_OUTER_ALPHABET,
)
from app.core.tracking.click_id_generator import generate_click_id_from_timestamp

logger = logging.getLogger(__name__)

_BEIJING = timezone(timedelta(hours=8))

# userinfo 内业务字段（紧凑 JSON 键名尽量短）
_KEY_OFFER = "oid"
_KEY_PUBLISHER = "pub"
_KEY_ADVERTISER = "aid"
_KEY_SHORT_LINK = "slid"
_KEY_URL_PARAMS = "up"

# 与 models / sql 中 click_id varchar(255) 一致
CLICK_ID_MAX_LENGTH = 255

# 短链接 URL 场景历史约束
CLICK_ID_SHORT_LINK_MAX_OUTER = 60


def click_id_max_length() -> int:
    return CLICK_ID_MAX_LENGTH


def tracking_token_max_outer_chars(*, for_short_link: bool = False) -> int:
    """紧凑令牌外层字符上限：短链 60，其余默认 255（可配置）。"""
    if for_short_link:
        return CLICK_ID_SHORT_LINK_MAX_OUTER
    cap = int(getattr(settings, "TRACKING_TOKEN_MAX_OUTER_CHARS", CLICK_ID_MAX_LENGTH))
    return min(max(cap, CLICK_ID_SHORT_LINK_MAX_OUTER), CLICK_ID_MAX_LENGTH)


def ensure_click_id_db_length(click_id: str) -> str:
    """保证写入数据库前不超过 click_id 列长度。"""
    if len(click_id) <= CLICK_ID_MAX_LENGTH:
        return click_id
    logger.error(
        "click_id 长度 %s 超过上限 %s，将截断（不应发生，请检查令牌生成）",
        len(click_id),
        CLICK_ID_MAX_LENGTH,
    )
    return click_id[:CLICK_ID_MAX_LENGTH]


def use_tracking_token() -> bool:
    """是否对新生成的 click_id 使用追踪令牌（默认关闭，不影响现网）。"""
    return bool(getattr(settings, "USE_TRACKING_TOKEN", False))


def _looks_like_tracking_token(click_id: str) -> bool:
    """粗筛：仅含 58 进制字母表字符才尝试解析，避免对旧随机串做无用解密。"""
    s = (click_id or "").strip()
    if not s or len(s) < 12:
        return False
    alphabet = set(TOKEN_OUTER_ALPHABET)
    return all(c in alphabet for c in s)


def _ms_to_naive_beijing(ts_ms: int) -> datetime:
    dt_utc = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    dt_bj = dt_utc.astimezone(_BEIJING)
    return dt_bj.replace(tzinfo=None)


def _pick_int(data: Dict[str, Any], *keys: str) -> Optional[int]:
    for k in keys:
        if k not in data or data[k] is None:
            continue
        try:
            return int(data[k])
        except (TypeError, ValueError):
            continue
    return None


def build_tracking_user_params(
    *,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None,
    advertiser_id: Optional[int] = None,
    short_link_id: Optional[int] = None,
    url_params: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """组装写入令牌 userinfo 的紧凑字段。"""
    params: Dict[str, Any] = {}
    if offer_id is not None:
        params[_KEY_OFFER] = int(offer_id)
    if publisher_id is not None:
        params[_KEY_PUBLISHER] = int(publisher_id)
    if advertiser_id is not None:
        params[_KEY_ADVERTISER] = int(advertiser_id)
    if short_link_id is not None:
        params[_KEY_SHORT_LINK] = int(short_link_id)
    if url_params:
        params[_KEY_URL_PARAMS] = url_params
    if extra:
        for k, v in extra.items():
            if k not in params and v is not None:
                params[k] = v
    return params


def generate_tracking_click_id(
    *,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None,
    advertiser_id: Optional[int] = None,
    short_link_id: Optional[int] = None,
    url_params: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    token_format: str = "auto",
    max_outer_chars: Optional[int] = None,
    for_short_link: bool = False,
) -> str:
    """
    生成带业务参数的追踪令牌。

    默认 ``auto``：在 max_outer_chars 内优先 compact，否则 full（总长 ≤255）。
    短链请设 ``for_short_link=True``（外层 ≤60）；普通追踪用 255。
    失败时回退旧版 ``generate_click_id_from_timestamp``，避免点击链路中断。
    """
    outer_cap = (
        max_outer_chars
        if max_outer_chars is not None
        else tracking_token_max_outer_chars(for_short_link=for_short_link)
    )

    def _try_generate(params: Optional[Dict[str, Any]], fmt: str) -> str:
        try:
            return AdTrackingCodec.generate(
                params,
                format=fmt,  # type: ignore[arg-type]
                max_outer_chars=outer_cap,
            )
        except ValueError:
            if fmt != "full":
                return AdTrackingCodec.generate(
                    params,
                    format="full",
                    max_outer_chars=outer_cap,
                )
            raise

    user_params = build_tracking_user_params(
        offer_id=offer_id,
        publisher_id=publisher_id,
        advertiser_id=advertiser_id,
        short_link_id=short_link_id,
        url_params=url_params,
        extra=extra,
    )
    fmt = token_format if token_format in ("compact", "full", "auto") else "auto"
    try:
        token = _try_generate(user_params or None, fmt)
        if len(token) > CLICK_ID_MAX_LENGTH and user_params and _KEY_URL_PARAMS in user_params:
            slim = {k: v for k, v in user_params.items() if k != _KEY_URL_PARAMS}
            logger.warning(
                "click_id 超过 %s，去掉 url_params 后重试",
                CLICK_ID_MAX_LENGTH,
            )
            token = _try_generate(slim or None, fmt)
        token = ensure_click_id_db_length(token)
        logger.debug(
            "追踪令牌已生成 offer=%s pub=%s aid=%s len=%s cap=%s",
            offer_id,
            publisher_id,
            advertiser_id,
            len(token),
            outer_cap,
        )
        return token
    except Exception as e:
        logger.warning(
            "追踪令牌生成失败，回退旧 click_id: %s (offer=%s pub=%s)",
            e,
            offer_id,
            publisher_id,
        )
        return generate_click_id_from_timestamp()


def generate_click_id_unified(
    *,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None,
    advertiser_id: Optional[int] = None,
    short_link_id: Optional[int] = None,
    url_params: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    for_short_link: bool = False,
) -> str:
    """
    统一入口：按配置选择新令牌或旧版随机 click_id。
    """
    if use_tracking_token():
        cid = generate_tracking_click_id(
            offer_id=offer_id,
            publisher_id=publisher_id,
            advertiser_id=advertiser_id,
            short_link_id=short_link_id,
            url_params=url_params,
            extra=extra,
            for_short_link=for_short_link,
        )
        return ensure_click_id_db_length(cid)
    legacy = generate_click_id_from_timestamp()
    return ensure_click_id_db_length(legacy)


def association_from_parsed(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """将 ``AdTrackingCodec.parse`` 结果转为 ClickAssociator 兼容字典。"""
    if not parsed.get("valid") or parsed.get("reason") != REASON_OK:
        return None

    ui = parsed.get("userinfo") or {}
    if not isinstance(ui, dict):
        ui = {}

    sysinfo = parsed.get("sysinfo") or {}
    ts_ms = sysinfo.get("timestamp_ms")
    click_time = _ms_to_naive_beijing(int(ts_ms)) if ts_ms is not None else None

    offer_id = _pick_int(ui, _KEY_OFFER, "offer_id", "oid")
    publisher_id = _pick_int(ui, _KEY_PUBLISHER, "publisher_id", "pub", "pid")
    advertiser_id = _pick_int(ui, _KEY_ADVERTISER, "advertiser_id", "aid")
    short_link_id = _pick_int(ui, _KEY_SHORT_LINK, "short_link_id", "slid")

    url_params = ui.get(_KEY_URL_PARAMS) or ui.get("url_params")
    if url_params is not None and not isinstance(url_params, dict):
        url_params = None

    return {
        "click_id": None,  # 由调用方填入
        "offer_id": offer_id,
        "publisher_id": publisher_id,
        "advertiser_id": advertiser_id,
        "short_link_id": short_link_id,
        "click_time": click_time,
        "ip": ui.get("ip"),
        "user_agent": ui.get("user_agent") or ui.get("ua"),
        "country": ui.get("country"),
        "device": ui.get("device"),
        "os": ui.get("os"),
        "offer": None,
        "publisher": None,
        "advertiser": None,
        "url_params": url_params or {},
        "_from_token": True,
    }


def resolve_click_from_token(click_id: str) -> Optional[Dict[str, Any]]:
    """
    仅从令牌解析归因（不访问数据库）。
    旧版随机 click_id 通常解析失败，由上层回退 DB。
    """
    if len(click_id) > CLICK_ID_MAX_LENGTH:
        logger.warning("click_id 超过数据库上限 %s，无法解析", CLICK_ID_MAX_LENGTH)
        return None
    if not click_id or not _looks_like_tracking_token(click_id):
        return None

    max_age = getattr(settings, "TRACKING_TOKEN_MAX_AGE_SECONDS", None)
    if max_age is not None and max_age > 0:
        verified = AdTrackingCodec.verify(click_id, max_age_seconds=float(max_age))
        if not verified.get("valid"):
            logger.info(
                "click_id 令牌校验未通过: %s reason=%s",
                click_id[:24],
                verified.get("reason"),
            )
            return None

    parsed = AdTrackingCodec.parse(click_id)
    assoc = association_from_parsed(parsed)
    if not assoc:
        logger.debug(
            "click_id 令牌解析失败: %s reason=%s",
            click_id[:24],
            parsed.get("reason"),
        )
        return None

    if not any(
        assoc.get(k) is not None
        for k in ("offer_id", "publisher_id", "advertiser_id")
    ):
        logger.warning("click_id 令牌无业务 ID: %s", click_id[:32])
        return None

    assoc["click_id"] = click_id
    logger.info(
        "click_id 令牌解析成功: offer=%s pub=%s aid=%s",
        assoc.get("offer_id"),
        assoc.get("publisher_id"),
        assoc.get("advertiser_id"),
    )
    return assoc


