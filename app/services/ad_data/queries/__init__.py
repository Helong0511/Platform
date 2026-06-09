"""
广告数据查询子模块包。

功能说明：
- 导出 list/detail/stats 等专用查询构建器，将复杂 SQL 从 service 中拆分

在系统中的位置：
- 被 ``app.services.ad_data.service`` 组合调用

注意事项：
1. 查询模块只做读操作，不写库、不提交事务
2. 新增查询类型应新增独立 query 文件，避免单文件过大
"""

from app.services.ad_data.queries.detail_query import DetailQueryBuilder
from app.services.ad_data.queries.list_query import ListQueryBuilder
from app.services.ad_data.queries.stats_query import StatsQueryBuilder

__all__ = [
    'ListQueryBuilder',
    'DetailQueryBuilder',
    'StatsQueryBuilder',
]
