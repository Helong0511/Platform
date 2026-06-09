"""
广告数据指标计算器包。

功能说明：
- 导出收入、比率等纯计算函数，供 service 与报表复用

在系统中的位置：
- 被 ``app.services.ad_data.service`` 在聚合结果后处理阶段调用

注意事项：
1. 计算器无 IO，仅做数值变换，便于单元测试
2. 除零与空值须返回约定默认值（0 或 None），勿抛未捕获异常
"""

from app.services.ad_data.calculators.rate_calculator import RateCalculator
from app.services.ad_data.calculators.revenue_calculator import RevenueCalculator

__all__ = [
    'RateCalculator',
    'RevenueCalculator',
]
