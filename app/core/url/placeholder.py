"""
统一占位符解析（Postback 转发 URL、短链跳转 URL 共用）。

- ``resolve_brace_placeholders``：替换 ``{click_id}`` 等花括号占位符（Postback 风格）
- ``normalize_placeholder_name`` / ``PLACEHOLDER_ALIAS_MAP``：短链 ``{clickId}`` 等别名
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.core.url.url_params_util import CLOAK_META_KEYS, scalar_query_value

logger = logging.getLogger(__name__)

# Postback 转发常用：花括号键 -> data 字段名
PLACEHOLDER_BRACE_MAP: Dict[str, str] = {
    "{click_id}": "click_id",
    "{clickid}": "click_id",
    "{conversion_id}": "conversion_id",
    "{payout}": "payout",
    "{event_name}": "event_name",
    "{offer_id}": "offer_id",
    "{publisher_id}": "publisher_id",
    "{advertiser_id}": "advertiser_id",
    "{ip}": "ip",
    "{country}": "country",
    "{os}": "os",
    "{device}": "device",
    "{short_link_id}": "short_link_id",
}

# 短链：占位符名（无花括号）-> 规范字段名
PLACEHOLDER_ALIAS_MAP: Dict[str, str] = {
    "clickid": "click_id",
    "clickId": "click_id",
    "clk_id": "click_id",
    "cid": "click_id",
    "aff_click_id": "click_id",
    "affclickid": "click_id",
    "publisherId": "publisher_id",
    "publisherid": "publisher_id",
    "channelId": "channel_id",
    "channelid": "channel_id",
    "sub_affid": "channel_id",
    "subaffid": "channel_id",
    "offerId": "offer_id",
    "offerid": "offer_id",
}

_BRACE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_DOUBLE_BRACE_PATTERN = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}")
# 检测单/双花括号占位符（build_final_url、merge 等）
ANY_NAMED_PLACEHOLDER_RE = re.compile(
    r"\{\{[a-zA-Z_][a-zA-Z0-9_]*\}\}|\{[a-zA-Z_][a-zA-Z0-9_]*\}"
)


def placeholder_delimiters(name: str) -> List[str]:
    """占位符字面量，长格式优先（先替换 ``{{name}}`` 再 ``{name}``）。"""
    return [f"{{{{{name}}}}}", f"{{{name}}}"]


def expand_brace_placeholder_variants(tokens: List[str]) -> List[str]:
    """为 ``{click_id}`` 等同名列表追加 ``{{click_id}}`` 双花括号形式。"""
    out: List[str] = []
    seen: set[str] = set()
    for token in tokens:
        for t in (token, "{" + token + "}" if token.startswith("{") and token.endswith("}") else token):
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


def replace_placeholder_literals(text: str, name: str, replacement: str) -> str:
    """将 text 中 ``{name}`` / ``{{name}}`` 均替换为 replacement。"""
    result = text
    for token in placeholder_delimiters(name):
        result = result.replace(token, replacement)
    return result


def text_has_named_placeholder(text: str, literal_tokens: List[str]) -> bool:
    """检测文本是否含给定占位符字面量（含双花括号扩展）。"""
    for token in expand_brace_placeholder_variants(literal_tokens):
        if token in text:
            return True
    return False


def normalize_placeholder_name(name: str) -> str:
    """规范化占位符名（别名、驼峰转下划线）。"""
    if not name:
        return name
    low = name.lower()
    if low in PLACEHOLDER_ALIAS_MAP:
        return PLACEHOLDER_ALIAS_MAP[low]
    if name in PLACEHOLDER_ALIAS_MAP:
        return PLACEHOLDER_ALIAS_MAP[name]
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _lookup_value(data: Dict[str, Any], field_name: str) -> Optional[Any]:
    url_params = data.get("url_params") or {}
    if isinstance(url_params, dict) and field_name in url_params:
        raw = url_params[field_name]
        if field_name in CLOAK_META_KEYS:
            return raw
        scalar = scalar_query_value(raw)
        if scalar is not None:
            return scalar
        return raw if not isinstance(raw, list) else None
    return data.get(field_name)


def resolve_brace_placeholders(url: str, data: Dict[str, Any]) -> str:
    """
    替换 URL 中的 ``{field}`` / ``{{field}}`` 占位符（Postback 渠道 URL 等）。
    """
    resolved = url
    for placeholder, field_name in PLACEHOLDER_BRACE_MAP.items():
        value = _lookup_value(data, field_name)
        if value is not None:
            inner = placeholder[1:-1]  # click_id from {click_id}
            resolved = replace_placeholder_literals(resolved, inner, str(value))
    unresolved = extract_brace_placeholders(resolved)
    if unresolved:
        logger.warning("未解析的占位符：%s", unresolved)
    return resolved


def extract_brace_placeholders(url: str) -> List[str]:
    """提取 URL 中所有 ``{...}`` 占位符字符串。"""
    return re.findall(r"\{[^}]+\}", url)


def find_named_placeholders(text: str) -> List[str]:
    """提取 ``{name}`` / ``{{name}}`` 中的 name 列表（短链逻辑用，去重保序）。"""
    seen: set[str] = set()
    names: List[str] = []

    for name in _DOUBLE_BRACE_PATTERN.findall(text):
        if name not in seen:
            seen.add(name)
            names.append(name)

    for m in _BRACE_PATTERN.finditer(text):
        start = m.start()
        end = m.end()
        if start > 0 and text[start - 1] == "{":
            continue
        if end < len(text) and text[end] == "}":
            continue
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names
