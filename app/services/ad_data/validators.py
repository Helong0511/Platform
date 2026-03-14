"""
广告数据验证器

验证广告数据的完整性和有效性
"""
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class AdDataValidator:
    """广告数据验证器"""
    
    @staticmethod
    def validate_update_data(
        update_data: Dict[str, Any],
        is_admin: bool
    ) -> Tuple[bool, List[str]]:
        """
        验证更新数据
        
        Args:
            update_data: 更新数据字典
            is_admin: 是否管理员
        
        Returns:
            tuple: (是否通过验证，错误消息列表)
        """
        errors = []
        
        # 权限检查
        if not is_admin:
            errors.append("仅管理员可以更新广告数据")
        
        # 字段验证
        numeric_fields = [
            'request_count', 'match_count', 'display_count',
            'click_count', 'pageviews', 'ecpm_before_deduct',
            'ecpm_after_deduct', 'revenue_before_deduct',
            'revenue_after_deduct'
        ]
        
        for field in numeric_fields:
            if field in update_data:
                value = update_data[field]
                if value is not None:
                    try:
                        float(value)
                        if float(value) < 0:
                            errors.append(f"{field} 不能为负数")
                    except (ValueError, TypeError):
                        errors.append(f"{field} 必须是数字")
        
        # 日期格式验证
        if 'date' in update_data:
            try:
                if isinstance(update_data['date'], str):
                    datetime.fromisoformat(update_data['date'])
            except ValueError:
                errors.append(f"日期格式错误：{update_data['date']}")
        
        if errors:
            logger.warning(f"广告数据验证失败：errors={errors}")
            return False, errors
        
        return True, []
