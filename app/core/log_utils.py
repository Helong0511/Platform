"""
日志辅助工具：PII 脱敏。

位于 app/core/ 基础设施层，供 third_party_report、审计日志等模块在写日志前
对邮箱、手机号、哈希值做掩码，避免敏感信息明文落盘。
"""
from __future__ import annotations

from typing import Optional


def mask_email(email: Optional[str]) -> str:
    """
    对邮箱做脱敏，保留首字符与 @ 后域名。

    Args:
        email: 原始邮箱字符串

    Returns:
        脱敏后的展示字符串；空值返回 ``(空)``，过短返回 ``***``
    """
    if not email or not str(email).strip():
        return "(空)"
    e = str(email).strip()
    at = e.find("@")
    if at <= 1:
        return "***"
    return f"{e[0]}***{e[at:]}"


def mask_phone(phone: Optional[str]) -> str:
    """
    对手机号做脱敏，保留前 3 位与末 2 位。

    Args:
        phone: 原始手机号字符串

    Returns:
        脱敏后的展示字符串；空值返回 ``(空)``，长度 ≤4 返回 ``****``
    """
    if not phone or not str(phone).strip():
        return "(空)"
    p = str(phone).strip()
    if len(p) <= 4:
        return "****"
    return f"{p[:3]}****{p[-2:]}"


def mask_hash_prefix(value: str, prefix_len: int = 8) -> str:
    """
    对哈希值仅展示前缀，用于日志中标识记录而不暴露完整摘要。

    Args:
        value: 哈希字符串（如 SHA256 十六进制）
        prefix_len: 保留的前缀长度，默认 8

    Returns:
        ``前缀...`` 形式；空值返回 ``(空)``，长度不超过 prefix_len 时原样返回
    """
    if not value:
        return "(空)"
    return f"{value[:prefix_len]}..." if len(value) > prefix_len else value
