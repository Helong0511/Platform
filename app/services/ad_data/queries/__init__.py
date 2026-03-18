"""
广告数据查询构建器模块
"""

from app.services.ad_data.queries.detail_query import DetailQueryBuilder
from app.services.ad_data.queries.list_query import ListQueryBuilder
from app.services.ad_data.queries.stats_query import StatsQueryBuilder

__all__ = [
    'ListQueryBuilder',
    'DetailQueryBuilder',
    'StatsQueryBuilder',
]
