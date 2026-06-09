"""
广告数据入参校验模块。

功能说明：
- 校验广告数据创建/更新/查询请求的日期范围、产品归属、数值字段合法性
- 在 service 写入或查询前统一拦截无效参数，减少数据库异常

在系统中的位置：
- 被 ``app.services.ad_data.service`` 在写操作与复杂查询前调用

注意事项：
1. 校验失败应抛出带 ErrorCode 的业务异常，而非裸 ValueError
2. 日期边界使用业务时区（北京时间）规则，与 ``get_app_now_naive`` 一致
"""
import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple

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
