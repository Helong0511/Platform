"""
数据标准化转换器

将不同平台的 Postback 数据格式转换为统一格式
"""
import logging
from decimal import Decimal, InvalidOperation
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
        # 与 BFT 等平台别名对齐
        click_id_raw = DataNormalizer._extract_click_id(raw_data)
        conversion_id = (
            raw_data.get('conversion_id')
            or raw_data.get('conversionId')
            or click_id_raw
        )

        payout_raw = raw_data.get('payout')
        if payout_raw is None or str(payout_raw).strip() == '':
            payout_raw = raw_data.get('amount')

        event_name = str(raw_data.get('event_name') or 'default').strip() or 'default'
        normalized = {
            'platform': platform,
            'conversion_id': str(conversion_id or '').strip(),
            'event_name': event_name,
            'event_value': DataNormalizer._parse_decimal(raw_data.get('event_value')),
            'payout': DataNormalizer._parse_decimal(payout_raw),
            'devad_id': raw_data.get('devad_id'),
            'os': raw_data.get('os'),
            'carrier': raw_data.get('carrier'),
            'ip': raw_data.get('ip'),
            'gid': raw_data.get('gid'),
            'click_id': click_id_raw,
            'product_id': DataNormalizer._parse_int(raw_data.get('product_id')),
            'client_id': DataNormalizer._parse_int(raw_data.get('client_id')),
            'raw_data': raw_data,  # 保存原始数据
        }
        
        logger.debug(f"数据标准化完成：platform={platform}, conversion_id={normalized['conversion_id']}")
        return normalized
    
    @staticmethod
    def _extract_click_id(raw_data: Dict[str, Any]) -> Optional[str]:
        """从 Postback 原始字段提取 click_id（多别名）。"""
        for key in (
            'click_id', 'clk_id', 'cid', 'clickid', 'clickId', 'ClickId',
            'aff_click_id', 'AFF_CLICK_ID', 'affclickid',
        ):
            val = raw_data.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return None

    @staticmethod
    def _parse_float(value: Any) -> Optional[float]:
        """解析浮点数（非金额场景）"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_decimal(value: Any) -> Optional[Decimal]:
        """解析 Decimal（金额场景，避免 float 精度丢失）"""
        if value is None:
            return None
        try:
            parsed = Decimal(str(value).strip())
            return parsed if parsed.is_finite() else None
        except (InvalidOperation, ValueError, TypeError):
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
