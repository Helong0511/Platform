"""
广告数据服务模块

生产 API 使用 ``app.services.ad_data.service.AdDataService``（经 ``ad_data_service`` 包路径导出）。
子包提供查询构建器、计算器、校验器，供逐步拆分使用。
"""

from app.services.ad_data.service import AdDataService, join_country_info_for_ad_data
from app.services.ad_data.calculators.rate_calculator import RateCalculator
from app.services.ad_data.calculators.revenue_calculator import RevenueCalculator
from app.services.ad_data.queries.detail_query import DetailQueryBuilder
from app.services.ad_data.queries.list_query import ListQueryBuilder
from app.services.ad_data.queries.stats_query import StatsQueryBuilder
from app.services.ad_data.validators import AdDataValidator

__all__ = [
    "AdDataService",
    "join_country_info_for_ad_data",
    "ListQueryBuilder",
    "DetailQueryBuilder",
    "StatsQueryBuilder",
    "RateCalculator",
    "RevenueCalculator",
    "AdDataValidator",
]
