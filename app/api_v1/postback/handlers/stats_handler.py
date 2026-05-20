"""统计信息 API 适配层。"""
from app.services.cpl.postback_stats_service import (
    PostbackStatsService,
    postback_stats_service,
)

StatsHandler = PostbackStatsService
stats_handler = postback_stats_service

__all__ = ["StatsHandler", "stats_handler"]
