"""Postback 统计信息 API 适配层。

导出 PostbackStatsService 实例，供管理端获取转化汇总、
按 Offer/渠道/时间维度的统计数据。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
from app.services.cpl.postback_stats_service import (
    PostbackStatsService,
    postback_stats_service,
)

StatsHandler = PostbackStatsService
stats_handler = postback_stats_service

__all__ = ["StatsHandler", "stats_handler"]
