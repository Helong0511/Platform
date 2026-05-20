"""
占位符解析器（Postback 转发）

实现委托 ``app.core.url.placeholder``，保持 ``PlaceholderResolver`` 类名兼容。
"""
from typing import Any, Dict

from app.core.url.placeholder import (
    PLACEHOLDER_BRACE_MAP,
    extract_brace_placeholders,
    resolve_brace_placeholders,
)


class PlaceholderResolver:
    """占位符解析器"""

    PLACEHOLDER_PATTERNS = PLACEHOLDER_BRACE_MAP

    @staticmethod
    def resolve(url: str, data: Dict[str, Any]) -> str:
        return resolve_brace_placeholders(url, data)

    @staticmethod
    def extract_placeholders(url: str) -> list:
        return extract_brace_placeholders(url)
