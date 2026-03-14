"""
广告数据服务模块

提供广告数据管理功能：
- 查询构建（列表、详情、统计）
- 比率计算
- 收益计算
- 数据验证
"""

from app.services.ad_data.ad_data_service import AdDataService
from app.services.ad_data.queries.list_query import ListQueryBuilder
from app.services.ad_data.queries.detail_query import DetailQueryBuilder
from app.services.ad_data.queries.stats_query import StatsQueryBuilder
from app.services.ad_data.calculators.rate_calculator import RateCalculator
from app.services.ad_data.calculators.revenue_calculator import RevenueCalculator
from app.services.ad_data.validators import AdDataValidator

__all__ = [
    'AdDataService',
    'ListQueryBuilder',
    'DetailQueryBuilder',
    'StatsQueryBuilder',
    'RateCalculator',
    'RevenueCalculator',
    'AdDataValidator',
]
