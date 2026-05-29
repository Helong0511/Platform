"""
渠道 Postback URL 占位符校验（与 ``resolve_brace_placeholders`` 可解析字段对齐）。
"""
from __future__ import annotations

from typing import FrozenSet, List, Optional, Set

from app.core.url.placeholder import (
    PLACEHOLDER_ALIAS_MAP,
    PLACEHOLDER_BRACE_MAP,
    find_named_placeholders,
    normalize_placeholder_name,
)
from app.core.url.placeholder_validation import (
    PlaceholderValidationResult,
    _find_malformed_brace_snippets,
    _strip_valid_placeholder_tokens,
    format_placeholder_validation_error,
)

# 运行时 ``PLACEHOLDER_BRACE_MAP`` 可替换字段 + 转化/点击上下文字段
_POSTBACK_RESOLVABLE: FrozenSet[str] = frozenset(
    set(PLACEHOLDER_BRACE_MAP.values())
    | {
        "event_value",
        "gaid",
        "idfa",
        "user_agent",
        "referer",
        "accept_language",
        "device_type",
        "channel_id",
    }
)


def canonical_postback_field(raw_name: str) -> str:
    """Postback 场景下的规范字段名（与 ``resolve_brace_placeholders`` 第二遍解析一致）。"""
    key = normalize_placeholder_name(raw_name)
    if key in ("channel_id", "sub_affid", "subid", "sub_id"):
        return "publisher_id"
    if key == "offer_payout":
        return "payout"
    return key


def _is_supported_postback_name(raw_name: str) -> bool:
    canonical = canonical_postback_field(raw_name)
    if canonical in _POSTBACK_RESOLVABLE:
        return True
    if raw_name in PLACEHOLDER_ALIAS_MAP:
        return canonical_postback_field(raw_name) in _POSTBACK_RESOLVABLE
    return False


def postback_placeholder_summary() -> str:
    return (
        "转化: {conversion_id}、{payout}、{event_name}、{event_value}；"
        "点击: {click_id}/{clickId}、{offer_id}、{publisher_id}/{channel_id}、{advertiser_id}；"
        "设备: {ip}/{CLIENT IP}、{os}、{country}、{gaid}/{GAID}、{idfa}/{IDFA}、"
        "{user_agent}/{CLIENT USER AGENT}、{accept_language}/{CLIENT LANGUAGE}；"
        "支持 {x} 与 {{x}}"
    )


def validate_postback_placeholders(url: Optional[str]) -> PlaceholderValidationResult:
    """校验渠道 Postback URL 占位符；``ok=False`` 时应阻止保存。"""
    result = PlaceholderValidationResult(ok=True)
    if not url or not str(url).strip():
        return result

    text = str(url).strip()
    if "{{{" in text or "}}}" in text:
        result.errors.append("占位符花括号层数不正确，仅支持 {name} 或 {{name}}")

    names = find_named_placeholders(text)
    result.placeholders = list(names)

    unknown: List[str] = [n for n in names if not _is_supported_postback_name(n)]
    if unknown:
        hints = ", ".join(f"{{{u}}}" for u in unknown[:5])
        more = f" 等{len(unknown)}个" if len(unknown) > 5 else ""
        result.errors.append(
            f"Postback URL 中包含不支持的占位符: {hints}{more}。"
            f"支持的占位符：{postback_placeholder_summary()}"
        )

    remainder = _strip_valid_placeholder_tokens(text, names)
    bad = _find_malformed_brace_snippets(remainder)
    if bad:
        sample = "、".join(repr(s) for s in bad[:5])
        result.errors.append(
            f"URL 中存在无法解析的花括号片段：{sample}。"
            "请检查拼写、括号是否成对，或是否含非法字符。"
        )

    result.ok = not result.errors
    return result
