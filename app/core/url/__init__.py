"""URL 与占位符统一工具。"""
from app.core.url.placeholder import (
    PLACEHOLDER_ALIAS_MAP,
    PLACEHOLDER_BRACE_MAP,
    extract_brace_placeholders,
    normalize_placeholder_name,
    resolve_brace_placeholders,
)

__all__ = [
    "PLACEHOLDER_ALIAS_MAP",
    "PLACEHOLDER_BRACE_MAP",
    "extract_brace_placeholders",
    "normalize_placeholder_name",
    "resolve_brace_placeholders",
]
