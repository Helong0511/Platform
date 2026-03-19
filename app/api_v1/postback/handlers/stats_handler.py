"""统计信息处理模块"""
import logging
from typing import Optional

from fastapi import Request, HTTPException
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


class StatsHandler:
    """统计信息处理器"""

    async def get_postback_stats(
            self,
            request: Request,
            platform: Optional[str],
            start_date: Optional[str],
            end_date: Optional[str],
            db: AsyncSession,
            current_user: User
    ):
        """
        获取 PostBack 统计信息（仅管理员）
        """
        try:
            # 构建查询
            query = select(
                PostbackConversion.platform,
                func.count(PostbackConversion.id).label("total_conversions"),
                func.sum(PostbackConversion.original_payout).label("total_original_payout"),
                func.sum(PostbackConversion.payout).label("total_payout"),
                func.sum(PostbackConversion.event_value).label("total_event_value"),
                func.count(func.distinct(PostbackConversion.event_name)).label("unique_events")
            )

            # 应用过滤条件
            conditions = []
            if platform:
                conditions.append(PostbackConversion.platform == platform)

            # 日期范围过滤（使用应用时区，与数据库时间一致）
            if start_date:
                try:
                    start_datetime = parse_date_to_app_timezone(start_date, is_end_date=False)
                    conditions.append(PostbackConversion.created_at >= start_datetime)
                except ValueError:
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail="起始日期格式错误，请使用 YYYY-MM-DD 格式"
                    )

            if end_date:
                try:
                    end_datetime = parse_date_to_app_timezone(end_date, is_end_date=True)
                    conditions.append(PostbackConversion.created_at <= end_datetime)
                except ValueError:
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail="结束日期格式错误，请使用 YYYY-MM-DD 格式"
                    )

            if conditions:
                query = query.where(and_(*conditions))

            # 按平台分组
            query = query.group_by(PostbackConversion.platform)
            query = query.order_by(PostbackConversion.platform)

            result = await db.execute(query)
            stats_rows = result.all()

            # 转换为响应格式
            stats_list = []
            for row in stats_rows:
                stats_list.append(PostbackStatsResponse(
                    platform=row.platform,
                    total_conversions=int(row.total_conversions or 0),
                    total_original_payout=float(row.total_original_payout or 0.0) if hasattr(row,
                                                                                         'total_original_payout') else None,
                    total_payout=float(row.total_payout or 0.0),
                    total_event_value=float(row.total_event_value or 0.0),
                    unique_events=int(row.unique_events or 0),
                    date_range={
                        "start": start_date or "",
                        "end": end_date or ""
                    } if start_date or end_date else None
                ))

            logger.info(
                f"管理员 {current_user.username} 查询 PostBack 统计信息: "
                f"platform={platform}, stats_count={len(stats_list)}"
            )

            return ResponseBaseSchema.success(
                data=stats_list,
                message=f"成功获取 {len(stats_list)} 个平台的统计信息"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"查询 PostBack 统计信息失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"查询失败：{str(e)}"
            )


stats_handler = StatsHandler()
