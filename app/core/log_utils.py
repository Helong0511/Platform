"""日志辅助：PII 脱敏等。"""
from __future__ import annotations

from typing import Optional


def mask_email(email: Optional[str]) -> str:
    if not email or not str(email).strip():
        return "(空)"
    e = str(email).strip()
    at = e.find("@")
    if at <= 1:
        return "***"
    return f"{e[0]}***{e[at:]}"


def mask_phone(phone: Optional[str]) -> str:
    if not phone or not str(phone).strip():
        return "(空)"
    p = str(phone).strip()
    if len(p) <= 4:
        return "****"
    return f"{p[:3]}****{p[-2:]}"


def mask_hash_prefix(value: str, prefix_len: int = 8) -> str:
    if not value:
        return "(空)"
    return f"{value[:prefix_len]}..." if len(value) > prefix_len else value
