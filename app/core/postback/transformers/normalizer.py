"""
数据标准化转换器

将不同平台的 Postback 数据格式转换为统一格式
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class DataNormalizer:
    """数据标准化转换器"""
    
    @staticmethod
    def normalize(
        raw_data: Dict[str, Any],
        platform: str
    ) -> Dict[str, Any]:
        """
        标准化 Postback 数据
        
        Args:
            raw_data: 原始请求数据
            platform: 平台名称
        
        Returns:
            dict: 标准化后的数据
        """
        # 获取转化ID（优先使用conversion_id，其次使用click_id，最后使用clk_id）
        conversion_id = raw_data.get('conversion_id') or raw_data.get('click_id') or raw_data.get('clk_id')
        
        normalized = {
            'platform': platform,
            'conversion_id': str(conversion_id or ''),
            'event_name': str(raw_data.get('event_name') or 'default'),
            'event_value': DataNormalizer._parse_float(raw_data.get('event_value')),
            'payout': DataNormalizer._parse_float(raw_data.get('payout') or raw_data.get('amount')),
            'devad_id': raw_data.get('devad_id'),
            'os': raw_data.get('os'),
            'carrier': raw_data.get('carrier'),
            'ip': raw_data.get('ip'),
            'gid': raw_data.get('gid'),
            'click_id': raw_data.get('click_id') or raw_data.get('clk_id'),
            'product_id': DataNormalizer._parse_int(raw_data.get('product_id')),
            'client_id': DataNormalizer._parse_int(raw_data.get('client_id')),
            'raw_data': raw_data,  # 保存原始数据
        }
        
        logger.debug(f"数据标准化完成：platform={platform}, conversion_id={normalized['conversion_id']}")
        return normalized
    
    @staticmethod
    def _parse_float(value: Any) -> Optional[float]:
        """解析浮点数"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _parse_int(value: Any) -> Optional[int]:
        """解析整数"""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
