"""
数据验证器

验证 Postback 数据的完整性和有效性
"""
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


class DataValidator:
    """数据验证器"""
    
    # 必填字段列表
    REQUIRED_FIELDS = ['conversion_id', 'event_name']
    
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
        
        # 检查必填字段
        for field in DataValidator.REQUIRED_FIELDS:
            if field not in raw_data or not raw_data[field]:
                errors.append(f"缺少必填字段：{field}")
        
        # 检查 conversion_id 格式
        conversion_id = raw_data.get('conversion_id', '')
        if conversion_id and len(str(conversion_id)) > 100:
            errors.append(f"conversion_id 过长：{len(str(conversion_id))} 字符（最大 100）")
        
        # 检查 event_name 格式
        event_name = raw_data.get('event_name', '')
        if event_name and len(str(event_name)) > 50:
            errors.append(f"event_name 过长：{len(str(event_name))} 字符（最大 50）")
        
        # 检查 event_value（如果有）
        event_value = raw_data.get('event_value')
        if event_value is not None:
            try:
                float(event_value)
            except (ValueError, TypeError):
                errors.append(f"event_value 格式错误：{event_value}（应为数字）")
        
        # 检查 payout（如果有）
        payout = raw_data.get('payout')
        if payout is not None:
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
