"""
数据验证器

验证 Postback 数据的完整性和有效性
"""
import logging
from typing import Dict, Any, List, Tuple

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
        
        # 检查是否有 click_id 或 conversion_id（两者等价）
        click_id = raw_data.get('click_id') or raw_data.get('conversion_id')
        if not click_id or not str(click_id).strip():
            errors.append("缺少必填字段：click_id 或 conversion_id")
        
        # 检查 click_id/conversion_id 格式
        if click_id and len(str(click_id)) > 200:
            errors.append(f"click_id/conversion_id 过长：{len(str(click_id))} 字符（最大 100）")
        
        # 检查 payout 是必填的
        payout = raw_data.get('payout')
        if not payout:
            errors.append("缺少必填字段：payout")
        
        # 检查 payout 格式
        if payout:
            try:
                float(payout)
            except (ValueError, TypeError):
                errors.append(f"payout 格式错误：{payout}（应为数字）")
        
        # 记录验证结果
        if errors:
            logger.warning(
                f"Postback 数据验证失败：platform={platform}, "
                f"errors={', '.join(errors)}"
            )
            return False, errors
        
        logger.debug(f"Postback 数据验证通过：platform={platform}")
        return True, []
