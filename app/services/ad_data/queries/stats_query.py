"""
统计查询构建器

构建广告数据统计查询
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
    """统计查询构建器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_daily_stats(
            self,
            product_id: int,
            date_from: date,
            date_to: date
    ) -> Dict[str, Any]:
        """
        获取每日统计
        
        Args:
            product_id: 产品 ID
            date_from: 开始日期
            date_to: 结束日期
        
        Returns:
            dict: 统计数据
        """
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
        获取汇总统计
        
        Args:
            product_id: 产品 ID
            date_from: 开始日期
            date_to: 结束日期
        
        Returns:
            dict: 汇总统计数据
        """
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

        # 计算比率
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
