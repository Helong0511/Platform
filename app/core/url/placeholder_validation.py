"""
短链 / Offer Tracklink 录入时的占位符校验。

支持 ``{name}`` 与 ``{{name}}``；非法语法或不支持的占位符在保存前报错。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from app.core.url.placeholder import (
    PLACEHOLDER_ALIAS_MAP,
    find_named_placeholders,
    normalize_placeholder_name,
    placeholder_delimiters,
)

# 与 replace_short_link_placeholders 可替换字段对齐（规范名）
_SUPPORTED_CANONICAL: Set[str] = {
    "click_id",
    "ip",
    "os",
    "device_type",
    "country",
    "user_agent",
    "referer",
    "accept_language",
    "gaid",
    "idfa",
    "offer_id",
    "offer_name",
    "advertiser_offer_id",
    "offer_payout",
    "affiliate_payout",
    "offer_country",
    "offer_category",
    "offer_type",
    "offer_status",
    "publisher_id",
    "channel_id",
    "publisher_name",
    "publisher_email",
    "advertiser_id",
    "advertiser_name",
    "advertiser_email",
}

# 规范名 -> 录入提示用别名示例
_PLACEHOLDER_HINTS: dict[str, str] = {
    "click_id": "{click_id}、{{click_id}}、{clickId}、{aff_click_id}",
    "offer_id": "{offer_id}、{{offer_id}}、{offerId}",
    "offer_payout": "{offer_payout}、{payout}",
    "channel_id": "{channel_id}、{{channel_id}}、{sub_affid}、{channelId}",
    "publisher_id": "{publisher_id}、{{publisher_id}}",
    "ip": "{ip}、{{ip}}",
    "os": "{os}、{{os}}",
    "country": "{country}、{{country}}",
    "device_type": "{device_type}",
    "user_agent": "{user_agent}",
    "referer": "{referer}",
    "accept_language": "{accept_language}、{CLIENT LANGUAGE}",
    "gaid": "{gaid}、{GAID}",
    "idfa": "{idfa}、{IDFA}",
    "offer_name": "{offer_name}",
    "advertiser_offer_id": "{advertiser_offer_id}",
    "advertiser_id": "{advertiser_id}",
    "advertiser_name": "{advertiser_name}",
}

_OFFER_RELATED: Set[str] = {
    "offer_id",
    "offer_name",
    "advertiser_offer_id",
    "offer_payout",
    "affiliate_payout",
    "offer_country",
    "offer_category",
    "offer_type",
    "offer_status",
    "advertiser_id",
    "advertiser_name",
    "advertiser_email",
}

_PUBLISHER_RELATED: Set[str] = {
    "publisher_id",
    "channel_id",
    "publisher_name",
    "publisher_email",
}

# 形如 {xxx} / {{xxx}}，但不符合标识符规则
_MALFORMED_BRACE_RE = re.compile(
    r"\{\{?[^{}]*\}\}?|\{[^{}]*\}|\{|\}"
)


@dataclass
class PlaceholderValidationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    placeholders: List[str] = field(default_factory=list)


def supported_placeholder_summary() -> str:
    """供错误提示展示的 supported 占位符摘要。"""
    parts = [
        "点击: {click_id}/{clickId}/{aff_click_id}",
        "产品: {offer_id}/{offerId}、{offer_name}、{advertiser_offer_id}、{offer_payout}/{payout}",
        "渠道: {channel_id}/{sub_affid}、{publisher_id}",
        "设备: {ip}/{CLIENT IP}、{os}、{country}、{device_type}、{user_agent}/{CLIENT USER AGENT}、{referer}、{gaid}/{GAID}、{idfa}/{IDFA}",
        "语言: {accept_language}/{CLIENT LANGUAGE}",
        "广告主: {advertiser_id}、{advertiser_name}",
        "支持单花括号 {x} 与双花括号 {{x}}",
    ]
    return "；".join(parts)


def _canonical_placeholder_name(raw_name: str) -> str:
    """占位符名 -> 规范字段名（与 replace 逻辑一致）。"""
    key = normalize_placeholder_name(raw_name)
    if key in ("channel_id", "sub_affid"):
        return "publisher_id"
    return key


def _is_supported_name(raw_name: str) -> bool:
    canonical = _canonical_placeholder_name(raw_name)
    if canonical in _SUPPORTED_CANONICAL:
        return True
    if raw_name in PLACEHOLDER_ALIAS_MAP:
        return True
    if normalize_placeholder_name(raw_name) in PLACEHOLDER_ALIAS_MAP.values():
        return True
    return False


def _strip_valid_placeholder_tokens(text: str, names: List[str]) -> str:
    remainder = text
    for name in names:
        for token in placeholder_delimiters(name):
            remainder = remainder.replace(token, "")
    return remainder


def _find_malformed_brace_snippets(text: str) -> List[str]:
    """找出无法被识别的花括号片段（用于语法错误提示）。"""
    snippets: List[str] = []
    for m in _MALFORMED_BRACE_RE.finditer(text):
        s = m.group(0)
        if s in ("{", "}"):
            snippets.append(s)
            continue
        inner = s.strip("{}").strip()
        normalized = normalize_placeholder_name(inner)
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", normalized):
            snippets.append(s[:80])
    # 去重保序
    seen: set[str] = set()
    out: List[str] = []
    for s in snippets:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def validate_track_url_placeholders(
    url: Optional[str],
    *,
    offer_id: Optional[int] = None,
    channel_id: Optional[int] = None,
    skip_association_warnings: bool = False,
) -> PlaceholderValidationResult:
    """
    校验 Tracklink / 短链 original_url 中的占位符。

    Returns:
        PlaceholderValidationResult: ``ok=False`` 时 ``errors`` 非空，应阻止保存。
    """
    result = PlaceholderValidationResult(ok=True)
    if not url or not str(url).strip():
        return result

    text = str(url).strip()
    if "{{{" in text or "}}}" in text:
        result.errors.append("占位符花括号层数不正确，仅支持 {name} 或 {{name}}，不支持三层 {{{name}}}")

    names = find_named_placeholders(text)
    result.placeholders = list(names)

    unknown: List[str] = []
    for name in names:
        if not _is_supported_name(name):
            unknown.append(name)

    if unknown:
        hints = []
        for u in unknown[:5]:
            hints.append(f"{{{u}}}/{{{{{u}}}}}")
        more = f" 等{len(unknown)}个" if len(unknown) > 5 else ""
        result.errors.append(
            f"不支持的占位符：{', '.join(hints)}{more}。"
            f"支持的占位符：{supported_placeholder_summary()}"
        )

    remainder = _strip_valid_placeholder_tokens(text, names)
    bad_snippets = _find_malformed_brace_snippets(remainder)
    if bad_snippets:
        sample = "、".join(repr(s) for s in bad_snippets[:5])
        result.errors.append(
            f"URL 中存在无法解析的花括号片段：{sample}。"
            "请检查是否拼写错误、缺少右括号，或使用了非法字符（仅允许字母、数字、下划线）。"
        )

    # 业务警告（不阻止保存）
    if not skip_association_warnings:
        canonical_used = {_canonical_placeholder_name(n) for n in names}
        if canonical_used & _OFFER_RELATED and offer_id is None:
            result.warnings.append(
                "URL 含产品/Offer 相关占位符，但未关联 Offer；运行时部分字段可能为空并被跳过。"
            )
        if canonical_used & _PUBLISHER_RELATED and channel_id is None and offer_id is None:
            result.warnings.append(
                "URL 含渠道相关占位符，但未关联渠道或 Offer；运行时渠道字段可能为空并被跳过。"
            )

    result.ok = not result.errors
    return result


def format_placeholder_validation_error(result: PlaceholderValidationResult) -> str:
    """合并为单条 ValueError / API detail 文案。"""
    return " ".join(result.errors)
