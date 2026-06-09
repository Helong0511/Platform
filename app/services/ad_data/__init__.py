"""
广告数据服务子包。

功能说明：
- 封装广告明细的查询、统计、校验与收入/比率计算
- 子模块分工：``service`` 主服务、``queries`` 查询构建、``calculators`` 指标计算、``validators`` 入参校验

在系统中的位置：
- 由 ``app.services.ad_data_service`` 统一导出；也可被定时任务、报表直接引用

注意事项：
1. 查询逻辑优先放入 queries，避免 service.py 无限膨胀
2. 日期与产品分配过滤需与 ``app.core.query_utils`` 约定保持一致
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
