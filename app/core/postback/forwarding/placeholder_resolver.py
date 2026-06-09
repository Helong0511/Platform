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
        """
        将 URL 中的 ``{name}`` / ``{{name}}`` 占位符替换为 data 中的实际值。

        Args:
            url: 含占位符的转发 URL 模板
            data: 点击/转化上下文字段字典

        Returns:
            替换后的完整 URL 字符串
        """
        return resolve_brace_placeholders(url, data)

    @staticmethod
    def extract_placeholders(url: str) -> list:
        """
        从 URL 模板中提取所有花括号占位符名称。

        Args:
            url: 转发 URL 模板

        Returns:
            占位符名列表（去重、保持出现顺序）
        """
        return extract_brace_placeholders(url)
