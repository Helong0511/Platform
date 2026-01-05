"""
Macan 平台 Postback 处理器
处理 Macan S2S PostBack 回调
"""
import logging
from typing import Dict, Any, Optional
from app.core.postback.handlers import PostbackHandler

logger = logging.getLogger(__name__)


class MacanPostbackHandler(PostbackHandler):
    """Macan 平台 Postback 处理器"""
    
    @property
    def platform_name(self) -> str:
        """返回平台名称"""
        return "macan"
    
    async def validate(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        验证 Macan postback 数据
        
        Macan 必填参数：
        - clk_id 或 cid: Macan click ID（必填）
        
        可选参数：
        - event_name: Event ID（事件ID，可选）
        """
        # 支持多种参数名：clk_id, click_id, cid, clickid, conversion_id 等
        clk_id = (
            data.get("clk_id") or
            data.get("click_id") or
            data.get("cid") or
            data.get("clickid") or
            data.get("clickId") or
            data.get("ClickId") or
            data.get("conversion_id") or
            data.get("conversionId")
        )
        
        # 只验证 clk_id 是必填的，event_name 是可选的
        if not clk_id or not str(clk_id).strip():
            return False, "clk_id 或 cid 参数不能为空"
        
        return True, None
    
    async def normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化 Macan postback 数据
        
        Macan 参数映射：
        - clk_id -> conversion_id
        - event_name -> event_name
        - devad_id -> devad_id
        - event_value -> event_value
        - payout -> payout
        - carrier -> carrier
        - os -> os
        - ip -> ip
        - gid -> gid
        - product_id -> product_id
        - client_id -> client_id
        """
        # 处理 clk_id（可能以不同字段名出现，包括 cid）
        conversion_id = (
            data.get("clk_id") or
            data.get("click_id") or
            data.get("cid") or
            data.get("clickid") or
            data.get("clickId") or
            data.get("ClickId") or
            data.get("conversion_id") or
            data.get("conversionId")
        )
        
        # 处理 event_name（可能以不同字段名出现）
        event_name = data.get("event_name") or data.get("event_id")
        
        # 处理 payout（支持多种字段名：payout, PayOut, pay_out, pay-out 等）
        payout = (
            data.get("payout") or
            data.get("PayOut") or
            data.get("pay_out") or
            data.get("pay-out") or
            data.get("Pay_Out") or
            data.get("Payout") or
            data.get("PAYOUT")
        )
        
        normalized = {
            "conversion_id": str(conversion_id).strip() if conversion_id else None,
            "event_name": str(event_name).strip() if event_name else None,
            "event_value": self._to_float(data.get("event_value")),
            "payout": self._to_float(payout),
            "devad_id": self._to_str(data.get("devad_id")),
            "os": self._to_str(data.get("os")),
            "carrier": self._to_str(data.get("carrier")),
            "ip": self._to_str(data.get("ip")),
            "gid": self._to_str(data.get("gid")),
            "product_id": self._to_int(data.get("product_id")),
            "client_id": self._to_int(data.get("client_id")),
        }
        
        return normalized
    
    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """转换为浮点数"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        """转换为整数"""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _to_str(value: Any) -> Optional[str]:
        """转换为字符串"""
        if value is None:
            return None
        return str(value).strip() if str(value).strip() else None

