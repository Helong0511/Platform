"""
广告数据统计查询构建器。

功能说明：
- 构建按日/月/产品/客户聚合的统计 SQL（展示、点击、收入等）
- 为仪表盘与报表提供高性能聚合查询基础

在系统中的位置：
- 被 ``AdDataService`` 统计与导出接口调用

注意事项：
1. 聚合查询注意 GROUP BY 字段与索引匹配，避免全表扫描
2. 空数据日期应补零或按前端约定返回，保持图表连续
"""
import logging
from datetime import date
from typing import Dict, Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import AdData, Product

logger = logging.getLogger(__name__)


class StatsQueryBuilder:
    """
    广告数据统计查询构建器。

    专注于单产品维度的 SQL 聚合，不涉及客户权限与产品分配历史表，
    适用于产品详情页的趋势图与 KPI 卡片展示。
    """

    def __init__(self, db: AsyncSession):
        """
        初始化构建器。

        Args:
            db: 异步数据库会话
        """
        self.db = db

    async def get_daily_stats(
            self,
            product_id: int,
            date_from: date,
            date_to: date
    ) -> Dict[str, Any]:
        """
        获取指定产品在日期区间内的每日聚合统计。

        SQL 逻辑：按 AdData.date 分组，对各项指标执行 SUM 聚合。

        Args:
            product_id: 产品主键 ID
            date_from: 统计起始日期（含）
            date_to: 统计结束日期（含）

        Returns:
            字典，键为 daily_stats，值为每日统计对象列表，每项含：
            date、request_count、match_count、display_count、click_count、revenue
        """

        # ── 按日分组聚合核心指标 ─────────────────────────────────────
        query = (
            select(
                AdData.date,
                func.sum(AdData.request_count).label('total_requests'),
                func.sum(AdData.match_count).label('total_matches'),
                func.sum(AdData.display_count).label('total_displays'),
                func.sum(AdData.click_count).label('total_clicks'),
                func.sum(AdData.revenue_after_deduct).label('total_revenue'),
            )
            .join(Product, AdData.product_id == Product.id)
            .where(AdData.product_id == product_id)
            .where(AdData.date >= date_from)
            .where(AdData.date <= date_to)
            .group_by(AdData.date)
        )

        result = await self.db.execute(query)
        rows = result.all()

        # ── 组装前端友好的字典列表 ───────────────────────────────────
        return {
            'daily_stats': [
                {
                    'date': row.date,
                    'request_count': row.total_requests,
                    'match_count': row.total_matches,
                    'display_count': row.total_displays,
                    'click_count': row.total_clicks,
                    'revenue': row.total_revenue,
                }
                for row in rows
            ]
        }

    async def get_summary_stats(
            self,
            product_id: int,
            date_from: date,
            date_to: date
    ) -> Dict[str, Any]:
        """
        获取指定产品在日期区间内的汇总统计及漏斗转化率。

        与 get_daily_stats 不同，本方法不分组，对整个区间做一次性 SUM，
        并在应用层计算覆盖率、展示率、点击率（避免除零）。

        Args:
            product_id: 产品主键 ID
            date_from: 统计起始日期（含）
            date_to: 统计结束日期（含）

        Returns:
            汇总字典，含 total_requests/matches/displays/clicks/revenue
            及 coverage_rate、display_rate、click_rate（保留两位小数）；
            无数据时返回空字典。
        """

        # ── 区间全量 SUM 聚合（无 GROUP BY）──────────────────────────
        query = (
            select(
                func.sum(AdData.request_count).label('total_requests'),
                func.sum(AdData.match_count).label('total_matches'),
                func.sum(AdData.display_count).label('total_displays'),
                func.sum(AdData.click_count).label('total_clicks'),
                func.sum(AdData.revenue_after_deduct).label('total_revenue'),
            )
            .join(Product, AdData.product_id == Product.id)
            .where(AdData.product_id == product_id)
            .where(AdData.date >= date_from)
            .where(AdData.date <= date_to)
        )

        result = await self.db.execute(query)
        row = result.first()

        if not row:
            return {}

        # ── 漏斗转化率计算（分母为 0 时返回 0）──────────────────────
        coverage_rate = (row.total_matches / row.total_requests * 100) if row.total_requests > 0 else 0
        display_rate = (row.total_displays / row.total_matches * 100) if row.total_matches > 0 else 0
        click_rate = (row.total_clicks / row.total_displays * 100) if row.total_displays > 0 else 0

        return {
            'total_requests': row.total_requests,
            'total_matches': row.total_matches,
            'total_displays': row.total_displays,
            'total_clicks': row.total_clicks,
            'total_revenue': row.total_revenue,
            'coverage_rate': round(coverage_rate, 2),
            'display_rate': round(display_rate, 2),
            'click_rate': round(click_rate, 2),
        }
