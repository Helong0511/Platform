"""
点击记录 url_params 读写规范化。

- **存库**：``dict[str, list[str]]``（保留重复 query）
- **业务读取**：扁平标量 dict（``normalize_url_params``）
"""
from __future__ import annotations

import json
from typing import Any, Dict, FrozenSet, List, Optional

# 平台写入的衍生字段（非原始 URL query），保持原类型
CLOAK_META_KEYS: FrozenSet[str] = frozenset({
    "cloak_visit",
    "cloak_dp_effective",
    "cloak_dp_query",
})


def scalar_query_value(value: Any) -> Optional[str]:
    """将 query 参数值规范为单个非空字符串；无法规范时返回 None。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, list):
        for item in value:
            s = scalar_query_value(item)
            if s is not None:
                return s
        return None
    s = str(value).strip()
    return s if s else None


def normalize_url_params(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    将 clicks.url_params（JSON）规范为业务读取用的扁平 dict。

    - 原始 query：``list[str]`` 取第一个非空标量；已是标量则 strip
    - 斗篷衍生字段（``cloak_*``）：原样保留
    """
    if not raw or not isinstance(raw, dict):
        return {}

    out: Dict[str, Any] = {}
    for key, value in raw.items():
        k = str(key)
        if k in CLOAK_META_KEYS:
            out[k] = value
            continue
        if isinstance(value, list):
            scalar = scalar_query_value(value)
            if scalar is not None:
                out[k] = scalar
        else:
            scalar = scalar_query_value(value)
            if scalar is not None:
                out[k] = scalar
            elif value is not None and not isinstance(value, (dict, list)):
                out[k] = str(value).strip()
    return out


def resolve_dp_from_url_params(url_params: Optional[Dict[str, Any]]) -> Optional[str]:
    """解析斗篷 dp：优先 ``cloak_dp_effective``，否则规范化 query 中的 ``dp``。"""
    if not url_params or not isinstance(url_params, dict):
        return None
    eff = scalar_query_value(url_params.get("cloak_dp_effective"))
    if eff:
        return eff
    return scalar_query_value(url_params.get("dp"))


def parse_stored_url_params(raw: Any, *, for_use: bool = True) -> Dict[str, Any]:
    """
    解析 clicks.url_params（JSON 字符串或 dict）。

    ``for_use=True`` 时返回业务用扁平 dict；``False`` 时返回解析后的原始 dict。
    """
    if not raw:
        return {}
    parsed: Optional[Dict[str, Any]] = None
    if isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                parsed = loaded
        except json.JSONDecodeError:
            return {}
    if not parsed:
        return {}
    return normalize_url_params(parsed) if for_use else parsed


def pack_query_params_for_storage(flat: Dict[str, Any]) -> Dict[str, List[str]]:
    """将标量 query 参数打包为落库用的 ``dict[str, list[str]]``。"""
    out: Dict[str, List[str]] = {}
    for key, value in flat.items():
        k = str(key)
        if k in CLOAK_META_KEYS:
            continue
        if isinstance(value, list):
            vals = [
                s
                for item in value
                if (s := scalar_query_value(item)) is not None
            ]
        else:
            s = scalar_query_value(value)
            vals = [s] if s is not None else []
        if vals:
            out[k] = vals
    return out


def needs_storage_canonicalization(raw: Dict[str, Any]) -> bool:
    """判断 url_params 是否含非 list 的 query 值（旧标量存库需迁移）。"""
    for key, value in raw.items():
        if str(key) in CLOAK_META_KEYS:
            continue
        if value is None:
            continue
        if not isinstance(value, list):
            return True
        if not value:
            return True
    return False


def canonicalize_url_params_for_storage(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    将任意形态的 url_params 规范为落库形态。

    - query 键：``dict[str, list[str]]``
    - ``cloak_*`` 衍生字段：保持 bool/str 等原类型
    """
    if not raw or not isinstance(raw, dict):
        return {}

    meta: Dict[str, Any] = {}
    query_flat: Dict[str, Any] = {}
    for key, value in raw.items():
        k = str(key)
        if k in CLOAK_META_KEYS:
            meta[k] = value
        elif value is not None:
            query_flat[k] = value

    packed = pack_query_params_for_storage(query_flat)
    return {**packed, **meta}


def canonicalize_url_params_json_text(raw_text: Optional[str]) -> Optional[str]:
    """
    解析 JSON 文本并规范为存库字符串；无需变更时返回 None（供迁移/落库去重）。
    """
    if not raw_text or not str(raw_text).strip():
        return None
    try:
        loaded = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict) or not loaded:
        return None
    if not needs_storage_canonicalization(loaded):
        return None
    canon = canonicalize_url_params_for_storage(loaded)
    if not canon:
        return None
    new_text = json.dumps(canon, ensure_ascii=False, separators=(",", ":"))
    if new_text == raw_text:
        return None
    return new_text


def merge_association_url_params(
    db_params: Any,
    token_params: Any,
) -> Dict[str, Any]:
    """
    合并 DB 与令牌中的 url_params（业务扁平 dict）。

    - 以 DB 为底；令牌侧非空标量覆盖同名 query 键
    - 令牌 ``url_params`` 为空 ``{}`` 时不覆盖 DB
    - ``cloak_*`` 元数据以 DB（桥页落库）为准
    """
    db_raw: Dict[str, Any] = db_params if isinstance(db_params, dict) else {}
    if not db_raw and isinstance(db_params, str):
        db_raw = parse_stored_url_params(db_params, for_use=False)
    db_norm = normalize_url_params(db_raw or None)

    token_raw: Dict[str, Any] = token_params if isinstance(token_params, dict) else {}
    token_norm = normalize_url_params(token_raw or None)

    if not token_norm:
        return db_norm
    if not db_norm:
        return token_norm

    merged = dict(db_norm)
    for key, value in token_norm.items():
        if key in CLOAK_META_KEYS:
            continue
        if value is not None and str(value).strip() != "":
            merged[key] = value
    for key in CLOAK_META_KEYS:
        if key in db_norm:
            merged[key] = db_norm[key]
    return merged


def build_click_association_payload(association: Dict[str, Any]) -> Dict[str, Any]:
    """Postback 转发/占位符使用的 click 上下文（``url_params`` 已规范化）。"""
    up = association.get("url_params")
    if isinstance(up, str):
        up_norm = parse_stored_url_params(up)
    else:
        up_norm = normalize_url_params(up if isinstance(up, dict) else None)
    return {
        "click_id": association.get("click_id"),
        "advertiser_id": association.get("advertiser_id"),
        "offer_id": association.get("offer_id"),
        "publisher_id": association.get("publisher_id"),
        "short_link_id": association.get("short_link_id"),
        "url_params": up_norm,
    }
