"""
Postback 统计查询服务。

功能说明：
- 按 platform 聚合 PostbackConversion 的转化数、payout、event_value 等指标
- 支持平台、日期区间筛选，供管理端报表与概览使用

在系统中的位置：
- 被 Postback 统计 API 与 Dashboard 子面板调用

注意事项：
1. 日期筛选使用 ``parse_date_to_app_timezone`` 统一边界
2. 聚合 SQL 注意索引（platform、conversion_time）命中
"""
import logging
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.utils import parse_date_to_app_timezone
from app.models.models import PostbackConversion, User
from app.schemas.base import ResponseBaseSchema
from app.schemas.postback import PostbackStatsResponse

logger = logging.getLogger(__name__)


class PostbackStatsService:
    """按平台聚合 Postback 转化数量与 payout 等业务指标。"""

    async def get_postback_stats(
        self,
        *,
        platform: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        db: AsyncSession,
        current_user: User,
    ):
        """
        查询 Postback 转化统计，按 platform 分组。

        Args:
            platform: 限定单个平台，None 表示全部平台分别统计。
            start_date / end_date: 可选日期边界 YYYY-MM-DD，过滤 created_at。
            db: 异步数据库会话。
            current_user: 当前用户，仅用于操作日志。

        Returns:
            ResponseBaseSchema，data 为 PostbackStatsResponse 列表，
            含 total_conversions、total_payout、unique_events 等字段。
        """
        try:
            query = select(
                PostbackConversion.platform,
                func.count(PostbackConversion.id).label("total_conversions"),
                func.sum(PostbackConversion.original_payout).label("total_original_payout"),
                func.sum(PostbackConversion.payout).label("total_payout"),
                func.sum(PostbackConversion.event_value).label("total_event_value"),
                func.count(func.distinct(PostbackConversion.event_name)).label("unique_events"),
            )

            conditions = []
            if platform:
                conditions.append(PostbackConversion.platform == platform)

            if start_date:
                try:
                    start_datetime = parse_date_to_app_timezone(start_date, is_end_date=False)
                    conditions.append(PostbackConversion.created_at >= start_datetime)
                except ValueError:
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail="起始日期格式错误，请使用 YYYY-MM-DD 格式",
                    )

            if end_date:
                try:
                    end_datetime = parse_date_to_app_timezone(end_date, is_end_date=True)
                    conditions.append(PostbackConversion.created_at <= end_datetime)
                except ValueError:
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail="结束日期格式错误，请使用 YYYY-MM-DD 格式",
                    )

            if conditions:
                query = query.where(and_(*conditions))

            query = query.group_by(PostbackConversion.platform).order_by(
                PostbackConversion.platform
            )
            result = await db.execute(query)
            stats_rows = result.all()

            stats_list: List[PostbackStatsResponse] = []
            for row in stats_rows:
                stats_list.append(
                    PostbackStatsResponse(
                        platform=row.platform,
                        total_conversions=int(row.total_conversions or 0),
                        total_original_payout=float(row.total_original_payout or 0.0)
                        if hasattr(row, "total_original_payout")
                        else None,
                        total_payout=float(row.total_payout or 0.0),
                        total_event_value=float(row.total_event_value or 0.0),
                        unique_events=int(row.unique_events or 0),
                        date_range={
                            "start": start_date or "",
                            "end": end_date or "",
                        }
                        if start_date or end_date
                        else None,
                    )
                )

            logger.info(
                f"管理员 {current_user.username} 查询 PostBack 统计: "
                f"platform={platform}, stats_count={len(stats_list)}"
            )
            return ResponseBaseSchema.success(
                data=stats_list,
                message=f"成功获取 {len(stats_list)} 个平台的统计信息",
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"查询 PostBack 统计信息失败: {e}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"查询失败：{str(e)}",
            )


postback_stats_service = PostbackStatsService()
