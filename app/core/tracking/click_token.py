"""
业务层 click_id 令牌：生成与解析，并与 Postback Click 关联结构兼容。

生产兼容策略：
- ``USE_TRACKING_TOKEN=false``（默认）：生成仍走旧版随机 click_id，与现网一致。
- 解析：粗筛 + verify 通过后 parse；失败则回退 ``clicks`` 表查询（旧 click_id 不受影响）。
- 生成：总长 ≤255；有用户 query 时**尽量**把 ``url_params`` 写入令牌（多档裁剪 + 多种编码），
  仅当全部带 ``up`` 的组合都塞不下时才去掉 ``up``。
"""
from __future__ import annotations

import logging
import struct
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.tracking.ad_tracking_codec import (
    AdTrackingCodec,
    REASON_OK,
    TOKEN_OUTER_ALPHABET,
)
from app.core.tracking.click_id_generator import (
    CLICK_ID_CHARS,
    generate_click_id_from_timestamp,
)

logger = logging.getLogger(__name__)

_BEIJING = timezone(timedelta(hours=8))

# userinfo 内业务字段（紧凑 JSON 键名尽量短）
_KEY_OFFER = "oid"
_KEY_PUBLISHER = "pub"
_KEY_ADVERTISER = "aid"
_KEY_SHORT_LINK = "slid"
_KEY_URL_PARAMS = "up"
# 短链场景：仅 ID 数组 [offer, publisher, advertiser, short_link?]，显著小于对象 JSON
_KEY_ID_LIST = "i"

# 与 models / sql 中 click_id varchar(255) 一致（全场景统一上限）
CLICK_ID_MAX_LENGTH = 255

# 向后兼容别名（历史短链 60 字符限制已取消，统一 255）
CLICK_ID_SHORT_LINK_MAX_OUTER = CLICK_ID_MAX_LENGTH

# url_params 写入令牌：先尽量完整嵌入，再逐级裁剪（仅实在塞不下才去掉 up）
_MAX_URL_PARAM_KEYS = 40
_MAX_URL_PARAM_VALUE_LEN = 160

# 裁剪到极限时仍尽量保留的常见追踪参数（按优先级）
_TRACKING_QUERY_KEYS: tuple[str, ...] = (
    "fbclid",
    "gclid",
    "clickid",
    "click_id",
    "aff_click_id",
    "sub_affid",
    "channel_id",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "cid",
    "clk_id",
)
# 已写入令牌主体（i/oid/pub 等）的 query 键，嵌入 up 时剔除以节省空间
_REDUNDANT_URL_PARAM_KEYS = frozenset({
    "offer_id",
    "channel_id",
    "publisher_id",
    "advertiser_id",
    "short_link_id",
    "oid",
    "pub",
    "aid",
    "slid",
    "click_id",
    "dp",
})
# 极限裁剪：仅保留广告点击 ID（Facebook 长 fbclid 场景）
_CLICK_ID_ONLY_KEYS: tuple[str, ...] = ("fbclid", "gclid", "clickid", "click_id")

# 旧版 click_id 字符集 ⊂ 令牌外层字母表；下列字符仅令牌可能出现
_LEGACY_ALPHABET = set(CLICK_ID_CHARS)
_TOKEN_ONLY_CHARS = set(TOKEN_OUTER_ALPHABET) - _LEGACY_ALPHABET


def click_id_max_length() -> int:
    """返回 click_id 数据库列上限（varchar 255）。"""
    return CLICK_ID_MAX_LENGTH


def tracking_token_max_outer_chars(*, for_short_link: bool = False) -> int:
    """令牌外层字符上限，与 click_id 列一致，默认 255（``for_short_link`` 不再单独限 60）。"""
    _ = for_short_link  # 保留参数以兼容调用方
    cap = int(getattr(settings, "TRACKING_TOKEN_MAX_OUTER_CHARS", CLICK_ID_MAX_LENGTH))
    return min(max(cap, 12), CLICK_ID_MAX_LENGTH)


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
    """
    粗筛：避免对典型旧版 ~40 位时间戳 ID 做无用 verify/parse。

    旧版字符集是 58 字母表的真子集；含「仅令牌」字符则必尝试解析。
    """
    s = (click_id or "").strip()
    if not s or len(s) < 12:
        return False
    if not all(c in TOKEN_OUTER_ALPHABET for c in s):
        return False
    if any(c in _TOKEN_ONLY_CHARS for c in s):
        return True
    # 纯旧版字母表且长度在典型旧 ID 区间 → 视为 legacy，直接走 DB
    if 36 <= len(s) <= 52 and all(c in _LEGACY_ALPHABET for c in s):
        return False
    return len(s) <= CLICK_ID_MAX_LENGTH


def _ms_to_naive_beijing(ts_ms: int) -> datetime:
    """将毫秒时间戳转为北京时间 naive datetime（与业务日期字段一致）。"""
    dt_utc = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    dt_bj = dt_utc.astimezone(_BEIJING)
    return dt_bj.replace(tzinfo=None)


def _pick_int(data: Dict[str, Any], *keys: str) -> Optional[int]:
    """从字典中按候选键顺序取第一个可解析为 int 的值。"""
    for k in keys:
        if k not in data or data[k] is None:
            continue
        try:
            return int(data[k])
        except (TypeError, ValueError):
            continue
    return None


def _ids_from_userinfo(ui: Dict[str, Any]) -> tuple[
    Optional[int], Optional[int], Optional[int], Optional[int]
]:
    """从 userinfo 解析 offer / publisher / advertiser / short_link。"""
    if _KEY_ID_LIST in ui:
        raw = ui[_KEY_ID_LIST]
        if isinstance(raw, list):
            vals: List[Optional[int]] = []
            for x in raw:
                try:
                    vals.append(int(x) if x is not None else None)
                except (TypeError, ValueError):
                    vals.append(None)
            while len(vals) < 4:
                vals.append(None)
            return vals[0], vals[1], vals[2], vals[3]

    return (
        _pick_int(ui, _KEY_OFFER, "offer_id", "oid"),
        _pick_int(ui, _KEY_PUBLISHER, "publisher_id", "pub", "pid"),
        _pick_int(ui, _KEY_ADVERTISER, "advertiser_id", "aid"),
        _pick_int(ui, _KEY_SHORT_LINK, "short_link_id", "slid"),
    )


def build_minimal_id_list_params(
    *,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None,
    advertiser_id: Optional[int] = None,
    short_link_id: Optional[int] = None,
) -> Dict[str, Any]:
    """短链紧凑载荷：``{"i":[oid,pub,aid,slid?]}``，仅去掉尾部 None。"""
    slots: List[Optional[int]] = [
        int(offer_id) if offer_id is not None else None,
        int(publisher_id) if publisher_id is not None else None,
        int(advertiser_id) if advertiser_id is not None else None,
        int(short_link_id) if short_link_id is not None else None,
    ]
    while len(slots) > 1 and slots[-1] is None:
        slots.pop()
    if not any(s is not None for s in slots):
        return {}
    return {_KEY_ID_LIST: slots}


def _filter_url_params_for_embedding(
    url_params: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """剔除已在令牌主体中的键，减小 up 体积（完整 query 仍存 clicks.url_params）。"""
    if not url_params or not isinstance(url_params, dict):
        return None
    filtered: Dict[str, Any] = {}
    for key, val in url_params.items():
        if val is None or str(key).lower() in _REDUNDANT_URL_PARAM_KEYS:
            continue
        filtered[key] = val
    return filtered or None


def _coerce_url_params(
    url_params: Dict[str, Any],
    *,
    max_keys: int,
    max_value_len: int,
    key_priority: Optional[tuple[str, ...]] = None,
    exclusive_keys: Optional[tuple[str, ...]] = None,
) -> Dict[str, Any]:
    """将 url_params 规范为可 JSON 序列化的扁平 dict（可控键数与值长）。"""
    items: List[tuple[str, Any]] = []
    seen: set[str] = set()

    def _add(key: str, val: Any) -> None:
        """向规范化列表追加键值，超长截断并去重。"""
        if val is None or key in seen or len(items) >= max_keys:
            return
        if isinstance(val, (dict, list)):
            try:
                import json as _json

                sval = _json.dumps(val, ensure_ascii=False, separators=(",", ":"))
            except Exception:
                sval = str(val)
        else:
            sval = str(val)
        if max_value_len > 0 and len(sval) > max_value_len:
            sval = sval[:max_value_len]
        if not sval and sval != "0":
            return
        seen.add(key)
        items.append((key, sval))

    lower_map = {str(k).lower(): (str(k), v) for k, v in url_params.items()}

    if exclusive_keys is not None:
        for pk in exclusive_keys:
            hit = lower_map.get(pk.lower())
            if hit:
                _add(hit[0][:64], hit[1])
        return dict(items)

    # 每一档都先写入追踪键，再写其余参数（尽量带上 fbclid/utm 等）
    priority = key_priority if key_priority is not None else _TRACKING_QUERY_KEYS
    for pk in priority:
        hit = lower_map.get(pk.lower())
        if hit:
            _add(hit[0][:64], hit[1])

    for k, v in url_params.items():
        _add(str(k)[:64], v)

    return dict(items)


def _url_params_slim_ladder(
    url_params: Optional[Dict[str, Any]],
) -> List[Optional[Dict[str, Any]]]:
    """
    生成多档 url_params，从「尽量完整」到「仅保留关键追踪键」。
    仅在所有档位均无法生成 ≤255 令牌时，上层才会尝试去掉 up。
    """
    if not url_params or not isinstance(url_params, dict):
        return [None]

    ladder: List[Optional[Dict[str, Any]]] = []
    seen: set[str] = set()

    def _push(d: Dict[str, Any]) -> None:
        """将一档 url_params 加入阶梯列表（按内容指纹去重）。"""
        if not d:
            return
        sig = tuple(sorted((k, str(v)) for k, v in d.items()))
        if sig in seen:
            return
        seen.add(sig)
        ladder.append(d)

    # 档位 0：尽量原样保留（追踪键优先，其次其余键；仅截断超长值）
    raw: Dict[str, Any] = {}
    raw_seen: set[str] = set()

    def _raw_put(key: str, val: Any) -> None:
        """档位 0：尽量原样保留键值，仅截断超长字符串。"""
        if key in raw_seen or len(raw) >= 40 or val is None:
            return
        if isinstance(val, (str, int, float, bool)):
            stored: Any = (
                val if not isinstance(val, str) else (val if len(val) <= 512 else val[:512])
            )
        else:
            try:
                import json as _json

                stored = _json.dumps(val, ensure_ascii=False, separators=(",", ":"))[:512]
            except Exception:
                stored = str(val)[:512]
        raw_seen.add(key)
        raw[key] = stored

    lower_map = {str(k).lower(): (str(k), v) for k, v in url_params.items()}
    for pk in _TRACKING_QUERY_KEYS:
        hit = lower_map.get(pk.lower())
        if hit:
            _raw_put(hit[0][:64], hit[1])
    for k, v in url_params.items():
        _raw_put(str(k)[:64], v)
    _push(raw)

    # 档位 1：较大限额（尽量多带）
    _push(_coerce_url_params(url_params, max_keys=80, max_value_len=512))
    _push(
        _coerce_url_params(
            url_params,
            max_keys=_MAX_URL_PARAM_KEYS,
            max_value_len=_MAX_URL_PARAM_VALUE_LEN,
        )
    )
    # 档位 2–4：逐步收紧
    for max_k, max_v in ((32, 120), (24, 80), (16, 48), (12, 32), (8, 24)):
        _push(_coerce_url_params(url_params, max_keys=max_k, max_value_len=max_v))
    # 档位 5：仅常见追踪键
    _push(
        _coerce_url_params(
            url_params,
            max_keys=len(_TRACKING_QUERY_KEYS),
            max_value_len=64,
            key_priority=_TRACKING_QUERY_KEYS,
        )
    )
    _push(
        _coerce_url_params(
            url_params,
            max_keys=len(_TRACKING_QUERY_KEYS),
            max_value_len=24,
            key_priority=_TRACKING_QUERY_KEYS,
        )
    )
    # 档位 6：仅广告点击 ID（长 fbclid + 多 utm 时仍能塞进 255）
    for max_k, max_v in ((3, 64), (2, 48), (1, 32), (1, 24)):
        _push(
            _coerce_url_params(
                url_params,
                max_keys=max_k,
                max_value_len=max_v,
                exclusive_keys=_CLICK_ID_ONLY_KEYS,
            )
        )
    return ladder if ladder else [None]


def _attach_url_params(
    base: Dict[str, Any],
    url_params: Dict[str, Any],
) -> Dict[str, Any]:
    """将 url_params 以紧凑键 ``up`` 并入令牌 userinfo 载荷。"""
    merged = dict(base)
    merged[_KEY_URL_PARAMS] = url_params
    return merged


def _params_fingerprint(p: Optional[Dict[str, Any]]) -> Optional[str]:
    """对 url_params 做稳定 JSON 序列化，用于生成尝试去重与日志标识。"""
    if not p:
        return None
    try:
        import json as _json

        return _json.dumps(p, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        return str(p)


def _build_generation_attempts(
    *,
    offer_id: Optional[int],
    publisher_id: Optional[int],
    advertiser_id: Optional[int],
    short_link_id: Optional[int],
    url_params: Optional[Dict[str, Any]],
    extra: Optional[Dict[str, Any]],
) -> List[Optional[Dict[str, Any]]]:
    """
    生成尝试序列：在 255 限制内**尽量保留 url_params**（多档裁剪 × 多种载荷），
    仅当全部带 up 的尝试均失败后才尝试无 up。
    """
    attempts: List[Optional[Dict[str, Any]]] = []
    seen_fp: set[str] = set()

    def _add(p: Optional[Dict[str, Any]]) -> None:
        """将一种载荷组合加入生成尝试序列（指纹去重）。"""
        if p is None:
            return
        fp = _params_fingerprint(p)
        if fp is None or fp in seen_fp:
            return
        seen_fp.add(fp)
        attempts.append(p)

    id_list_base = build_minimal_id_list_params(
        offer_id=offer_id,
        publisher_id=publisher_id,
        advertiser_id=advertiser_id,
        short_link_id=short_link_id,
    )

    up_ladder = _url_params_slim_ladder(url_params)
    has_up = url_params and isinstance(url_params, dict) and bool(url_params)

    if has_up:
        for up in up_ladder:
            if not up:
                continue
            # 紧凑 ID + up（体积最小，尽量塞下更多 query）
            if id_list_base:
                _add(_attach_url_params(id_list_base, up))
            # 标准对象 + up（兼容旧解析键名）
            _add(
                build_tracking_user_params(
                    offer_id=offer_id,
                    publisher_id=publisher_id,
                    advertiser_id=advertiser_id,
                    short_link_id=short_link_id,
                    url_params=up,
                    extra=extra,
                    minimal=False,
                )
            )

    # 最后手段：去掉 up（仅在上面的带 up 尝试全部失败后才会走到这里）
    if id_list_base:
        _add(id_list_base)
    _add(
        build_tracking_user_params(
            offer_id=offer_id,
            publisher_id=publisher_id,
            advertiser_id=advertiser_id,
            short_link_id=short_link_id,
            url_params=None,
            extra=extra,
            minimal=False,
        )
    )

    if not attempts:
        attempts.append(None)
    return attempts


def _formats_for_attempt(
    params: Optional[Dict[str, Any]],
    base_fmt: str,
) -> List[str]:
    """含 url_params 时多试 full（zlib），尽量把 query 塞进 255。"""
    if not params or _KEY_URL_PARAMS not in params:
        if base_fmt == "compact":
            return ["compact", "auto"]
        return [base_fmt] if base_fmt != "auto" else ["auto", "compact"]

    if base_fmt == "full":
        return ["full", "auto", "compact"]
    if base_fmt == "compact":
        return ["compact", "full", "auto"]
    return ["auto", "full", "compact"]


def build_tracking_user_params(
    *,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None,
    advertiser_id: Optional[int] = None,
    short_link_id: Optional[int] = None,
    url_params: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    minimal: bool = False,
) -> Dict[str, Any]:
    """组装写入令牌 userinfo 的字段。``minimal=True`` 时仅用 ID 数组（短链）。"""
    if minimal:
        return build_minimal_id_list_params(
            offer_id=offer_id,
            publisher_id=publisher_id,
            advertiser_id=advertiser_id,
            short_link_id=short_link_id,
        )

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

    外层长度上限统一为 ``CLICK_ID_MAX_LENGTH``(255)。有 ``url_params`` 时多档裁剪、
    多种编码反复尝试以**尽量**保留 up；仅当全部失败后才去掉 up，再失败则回退旧 click_id。
    """
    _ = for_short_link  # 兼容参数，不再单独限制 60 字符
    raw_url_params = url_params
    url_params = _filter_url_params_for_embedding(url_params)
    outer_cap = (
        min(int(max_outer_chars), CLICK_ID_MAX_LENGTH)
        if max_outer_chars is not None
        else tracking_token_max_outer_chars()
    )

    def _try_generate(params: Optional[Dict[str, Any]], fmt: str) -> str:
        """按 compact/full/auto 多格式尝试生成追踪令牌，失败抛最后一次异常。"""
        last: Optional[Exception] = None
        for use_fmt in _formats_for_attempt(params, fmt):
            try:
                return AdTrackingCodec.generate(
                    params,
                    format=use_fmt,  # type: ignore[arg-type]
                    max_outer_chars=outer_cap,
                    allow_full=True,
                )
            except (ValueError, RuntimeError) as e:
                last = e
        if last:
            raise last
        raise ValueError("无法生成追踪令牌")

    fmt = token_format if token_format in ("compact", "full", "auto") else "auto"
    all_attempts = _build_generation_attempts(
        offer_id=offer_id,
        publisher_id=publisher_id,
        advertiser_id=advertiser_id,
        short_link_id=short_link_id,
        url_params=url_params,
        extra=extra,
    )
    # 阶段一：仅带 up；阶段二：无 up（仅当阶段一全部失败才执行）
    with_up_attempts = [
        a for a in all_attempts if a and _KEY_URL_PARAMS in a
    ]
    without_up_attempts = [
        a for a in all_attempts if not a or _KEY_URL_PARAMS not in a
    ]

    last_error: Optional[Exception] = None
    had_url_params_to_embed = bool(url_params and isinstance(url_params, dict))

    def _attempt_once(attempt_params: Optional[Dict[str, Any]]) -> Optional[str]:
        """单次生成尝试：校验长度上限与 DB click_id 字段长度。"""
        nonlocal last_error
        try:
            token = _try_generate(attempt_params, fmt)
            if len(token) > CLICK_ID_MAX_LENGTH:
                last_error = ValueError(
                    f"令牌长度 {len(token)} 超过上限 {CLICK_ID_MAX_LENGTH}"
                )
                return None
            return ensure_click_id_db_length(token)
        except (ValueError, RuntimeError, struct.error) as e:
            last_error = e
            return None
        except Exception as e:
            last_error = e
            return None

    try:
        for attempt_params in with_up_attempts:
            token = _attempt_once(attempt_params)
            if not token:
                continue
            up_map = (attempt_params or {}).get(_KEY_URL_PARAMS) or {}
            logger.debug(
                "追踪令牌已生成（含 url_params）offer=%s pub=%s len=%s up_keys=%s",
                offer_id,
                publisher_id,
                len(token),
                len(up_map),
            )
            return token

        for attempt_params in without_up_attempts:
            token = _attempt_once(attempt_params)
            if not token:
                continue
            if had_url_params_to_embed:
                raw_n = len(raw_url_params) if isinstance(raw_url_params, dict) else 0
                embed_n = len(url_params) if isinstance(url_params, dict) else 0
                logger.warning(
                    "click_id 已生成但未嵌入 url_params（255 内所有带 up 尝试均失败）"
                    " offer=%s pub=%s len=%s raw_keys=%s embed_keys=%s",
                    offer_id,
                    publisher_id,
                    len(token),
                    raw_n,
                    embed_n,
                )
            else:
                logger.debug(
                    "追踪令牌已生成 offer=%s pub=%s len=%s",
                    offer_id,
                    publisher_id,
                    len(token),
                )
            return token

        if last_error:
            raise last_error
        raise ValueError("无法生成追踪令牌")
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

    offer_id, publisher_id, advertiser_id, short_link_id = _ids_from_userinfo(ui)

    url_params = ui.get(_KEY_URL_PARAMS) or ui.get("url_params")
    if url_params is not None and not isinstance(url_params, dict):
        url_params = None
    else:
        from app.core.url.url_params_util import normalize_url_params

        url_params = normalize_url_params(url_params) if url_params else {}

    return {
        "click_id": None,
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
    旧版随机 click_id 由粗筛跳过或 verify 失败后由上层回退 DB。
    """
    if len(click_id) > CLICK_ID_MAX_LENGTH:
        logger.warning("click_id 超过数据库上限 %s，无法解析", CLICK_ID_MAX_LENGTH)
        return None
    if not click_id or not _looks_like_tracking_token(click_id):
        return None

    max_age = getattr(settings, "TRACKING_TOKEN_MAX_AGE_SECONDS", None)
    max_age_arg = float(max_age) if max_age is not None and max_age > 0 else None
    verified = AdTrackingCodec.verify(click_id, max_age_seconds=max_age_arg)
    if not verified.get("valid"):
        logger.debug(
            "click_id 未通过令牌校验: %s reason=%s",
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


def regenerate_click_id_from_click_data(click_data: Dict[str, Any]) -> str:
    """碰撞重试时按原点击上下文重新生成 click_id。"""
    url_params: Optional[Dict[str, Any]] = None
    raw_up = click_data.get("url_params")
    if isinstance(raw_up, dict):
        from app.core.url.url_params_util import normalize_url_params

        url_params = normalize_url_params(raw_up)
    elif isinstance(raw_up, str) and raw_up.strip():
        try:
            import json as _json

            parsed = _json.loads(raw_up)
            if isinstance(parsed, dict):
                from app.core.url.url_params_util import normalize_url_params

                url_params = normalize_url_params(parsed)
        except Exception:
            pass

    return generate_click_id_unified(
        offer_id=click_data.get("offer_id"),
        publisher_id=click_data.get("publisher_id"),
        advertiser_id=click_data.get("advertiser_id"),
        short_link_id=click_data.get("short_link_id"),
        url_params=url_params,
    )

