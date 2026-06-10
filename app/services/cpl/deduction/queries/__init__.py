"""扣减查询子模块。"""

from app.services.cpl.deduction.queries.config_list_query import DeductionConfigListQuery
from app.services.cpl.deduction.queries.logs_query import DeductionLogsQuery
from app.services.cpl.deduction.queries.stats_query import DeductionStatsQuery

__all__ = [
    "DeductionConfigListQuery",
    "DeductionLogsQuery",
    "DeductionStatsQuery",
]
