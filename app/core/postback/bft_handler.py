"""
BFT 平台 Postback 处理器
处理 BFT S2S PostBack 回调
"""
import logging
from typing import Dict, Any, Optional
from app.core.postback.handlers import PostbackHandler
from app.core.postback.transformers.normalizer import DataNormalizer
from app.core.postback.validators.data_validator import validate_payout_value

logger = logging.getLogger(__name__)


class BftPostbackHandler(PostbackHandler):
    """BFT 平台 Postback 处理器"""
    
    @property
    def platform_name(self) -> str:
        """返回平台名称"""
        return "bft"
    
    async def validate(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """验证 BFT 回调字段；金额校验与通用入口使用同一 Decimal 规则。"""
        clk_id = self._first_non_empty(
            data,
            "clk_id", "click_id", "cid", "clickid", "clickId", "ClickId",
            "conversion_id", "conversionId",
        )
        if clk_id is None:
            return False, "clk_id 或 click_id 或 cid 参数不能为空"
        if len(str(clk_id).strip()) > 200:
            return False, "click_id/conversion_id 过长（最大 200 字符）"

        payout = self._first_non_empty(
            data,
            "payout", "PayOut", "pay_out", "pay-out", "Pay_Out", "Payout", "PAYOUT",
        )
        payout_error = validate_payout_value(payout)
        if payout_error:
            return False, payout_error

        event_name = self._first_non_empty(data, "event_name", "event_id")
        if event_name is not None and len(str(event_name)) > 100:
            return False, "event_name 过长（最大 100 字符）"

        return True, None

    async def normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化 BFT 回调；金额使用 Decimal，避免 float 精度损失。"""
        conversion_id = self._first_non_empty(
            data,
            "clk_id", "click_id", "cid", "clickid", "clickId", "ClickId",
            "conversion_id", "conversionId",
        )
        event_name_raw = self._first_non_empty(data, "event_name", "event_id")
        event_name = str(event_name_raw).strip() if event_name_raw is not None else "default"
        event_name = event_name or "default"

        payout = self._first_non_empty(
            data,
            "payout", "PayOut", "pay_out", "pay-out", "Pay_Out", "Payout", "PAYOUT",
        )

        return {
            "platform": self.platform_name,
            "conversion_id": str(conversion_id).strip() if conversion_id is not None else None,
            "event_name": event_name,
            "event_value": DataNormalizer._parse_decimal(data.get("event_value")),
            "payout": DataNormalizer._parse_decimal(payout),
            "devad_id": self._to_str(data.get("devad_id")),
            "os": self._to_str(data.get("os")),
            "carrier": self._to_str(data.get("carrier")),
            "ip": self._to_str(data.get("ip")),
            "gid": self._to_str(data.get("gid")),
            "product_id": self._to_int(data.get("product_id")),
            "client_id": self._to_int(data.get("client_id")),
            "click_id": str(conversion_id).strip() if conversion_id is not None else None,
            "raw_data": data,
        }

    @staticmethod
    def _first_non_empty(data: Dict[str, Any], *keys: str) -> Optional[Any]:
        """按字段优先级读取非空值；保留数值 0 供校验拒绝，不错误回退到别名。"""
        for key in keys:
            value = data.get(key)
            if value is not None and str(value).strip() != "":
                return value
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

