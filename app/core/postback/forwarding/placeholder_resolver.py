"""
占位符解析器

替换 Postback URL 中的占位符
"""
import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class PlaceholderResolver:
    """占位符解析器"""
    
    # 常见占位符模式
    PLACEHOLDER_PATTERNS = {
        '{click_id}': 'click_id',
        '{conversion_id}': 'conversion_id',
        '{payout}': 'payout',
        '{event_name}': 'event_name',
        '{offer_id}': 'offer_id',
        '{publisher_id}': 'publisher_id',
        '{advertiser_id}': 'advertiser_id',
        '{ip}': 'ip',
        '{country}': 'country',
        '{os}': 'os',
        '{device}': 'device',
    }
    
    @staticmethod
    def resolve(url: str, data: Dict[str, Any]) -> str:
        """
        替换 URL 中的占位符
        
        Args:
            url: 包含占位符的 URL
            data: 数据字典
        
        Returns:
            str: 替换后的 URL
        """
        resolved_url = url
        
        for placeholder, field_name in PlaceholderResolver.PLACEHOLDER_PATTERNS.items():
            value = data.get(field_name)
            if value is not None:
                # 替换占位符
                resolved_url = resolved_url.replace(placeholder, str(value))
                logger.debug(f"替换占位符 {placeholder} -> {value}")
        
        # 处理未解析的占位符（删除或保留）
        unresolved = re.findall(r'\{[^}]+\}', resolved_url)
        if unresolved:
            logger.warning(f"未解析的占位符：{unresolved}")
        
        return resolved_url
    
    @staticmethod
    def extract_placeholders(url: str) -> list:
        """
        提取 URL 中的所有占位符
        
        Args:
            url: URL 字符串
        
        Returns:
            list: 占位符列表
        """
        return re.findall(r'\{[^}]+\}', url)
