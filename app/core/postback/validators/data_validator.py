"""
数据验证器

验证 Postback 数据的完整性和有效性
"""
import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Tuple

from app.core.postback.transformers.normalizer import DataNormalizer

logger = logging.getLogger(__name__)


class DataValidator:
    """数据验证器"""
    
    @staticmethod
    def validate(
        raw_data: Dict[str, Any],
        platform: str
    ) -> Tuple[bool, List[str]]:
        """
        验证 Postback 数据
        
        Args:
            raw_data: 原始请求数据
            platform: 平台名称
        
        Returns:
            tuple: (是否通过验证，错误消息列表)
        """
        errors = []
        
        # 与标准化器保持一致，接受 click_id / conversion_id 及平台常见别名。
        conversion_id = raw_data.get('conversion_id') or raw_data.get('conversionId')
        click_id = DataNormalizer._extract_click_id(raw_data) or conversion_id
        if not click_id or not str(click_id).strip():
            errors.append("缺少必填字段：click_id 或 conversion_id")

        # Click / Conversion ID 最大长度与接口字段约束保持一致。
        if click_id and len(str(click_id).strip()) > 200:
            errors.append(
                f"click_id/conversion_id 过长：{len(str(click_id).strip())} 字符（最大 200）"
            )

        # 事件名入库字段为 VARCHAR(100)，提前拒绝超长数据，避免数据库截断/异常。
        event_name = raw_data.get('event_name')
        if event_name is not None and len(str(event_name)) > 100:
            errors.append("event_name 过长（最大 100 字符）")

        # payout 是必填正数；兼容标准化器支持的 amount 别名，并严格校验 Decimal。
        payout = raw_data.get('payout')
        if payout is None or str(payout).strip() == '':
            payout = raw_data.get('amount')

        if payout is None or str(payout).strip() == '':
            errors.append("缺少必填字段：payout")
        else:
            try:
                payout_val = Decimal(str(payout).strip())
                if not payout_val.is_finite():
                    errors.append(f"payout 必须为有限数字：当前值={payout}")
                elif payout_val <= 0:
                    errors.append(f"payout 必须大于 0：当前值={payout}")
                elif payout_val > Decimal("99999999.9999"):
                    errors.append("payout 超出数据库 Numeric(12, 4) 可存储范围")
                elif payout_val != payout_val.quantize(Decimal("0.0001")):
                    errors.append("payout 最多允许 4 位小数")
            except (InvalidOperation, ValueError, TypeError):
                errors.append(f"payout 格式错误：{payout}（应为有限数字）")

        # 记录验证结果
        if errors:
            logger.warning(
                f"Postback 数据验证失败：platform={platform}, "
                f"errors={', '.join(errors)}"
            )
            return False, errors
        
        logger.debug(f"Postback 数据验证通过：platform={platform}")
        return True, []
