"""仪表盘统计API端点
提供数据统计和趋势分析功能，包括：
- 获取仪表盘统计数据（按天、周、月、上月）
- 获取趋势数据（按日期分组）
- 计算各种指标（覆盖率、展示率、点击率、ROI等）
- 管理员可查看所有数据，客户只能查看自己的数据。

说明：REST API 端点，统一 ResponseBaseSchema 响应；鉴权由各端点 Depends 声明。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from app.core.database import get_db
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.dependencies import get_dashboard_service
from app.services.dashboard_service import DashboardService
from app.schemas.ad_data import DashboardStatsResponse, TrendDataResponse
from app.schemas.base import ResponseBaseSchema
from app.core.security import get_current_user
from app.models.models import User

# 创建路由实例
router = APIRouter()


@router.get("/stats", response_model=ResponseBaseSchema[DashboardStatsResponse])
async def get_dashboard_stats(period: str = "week", db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    """
    获取仪表盘统计数据（已重构使用服务层）
    - 支持按天、周、月、上月统计
    - 管理员可查看所有数据
    - 客户只能查看自己的数据
    - 使用缓存提升性能（缓存 1 分钟）
    """
    logger = logging.getLogger(__name__)

    # 使用服务层（业务逻辑在DashboardService中）
    dashboard_service: DashboardService = await get_dashboard_service(db)

    try:
        # 调用服务层获取仪表盘统计数据（服务层会处理查询、过滤、缓存、趋势计算等）
        response_data = await dashboard_service.get_dashboard_stats(
            period=period,
            current_user=current_user
        )
        
        return ResponseBaseSchema.success(data=DashboardStatsResponse(**response_data))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取仪表盘统计数据失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取统计数据失败：{str(e)}"
        )


@router.get("/recent-ads", response_model=ResponseBaseSchema[dict])
async def get_recent_ad_data(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    获取最近的广告数据（已重构使用服务层）
    - 返回最近7天的广告数据汇总
    - 管理员可查看所有数据
    - 客户只能查看自己的数据
    """
    # 使用服务层（业务逻辑在DashboardService中）
    dashboard_service: DashboardService = await get_dashboard_service(db)
    
    try:
        # 调用服务层获取最近广告数据（服务层会处理查询、过滤等）
        response_data = await dashboard_service.get_recent_ad_data(
            current_user=current_user,
            days=7
        )
        
        return ResponseBaseSchema.success(data=response_data)
    except Exception as e:
        logger.error(f"获取最近广告数据失败: {str(e)}")
        # 返回空数据而不是抛出异常，保持健壮性
        return ResponseBaseSchema.success(data={
            "ads": [],
            "summary": {
                "total_ads": 0,
                "active_ads": 0,
                "total_impressions": 0
            }
        })


@router.get("/trends", response_model=ResponseBaseSchema[TrendDataResponse])
async def get_trend_data(period: str = "week", db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """
    获取趋势数据（已重构使用服务层）
    - 支持按天、周、月、上月统计
    - 管理员可查看所有数据
    - 客户只能查看自己的数据
    - 使用缓存提升性能（缓存 1 分钟）
    """
    logger = logging.getLogger(__name__)

    # 使用服务层（业务逻辑在DashboardService中）
    dashboard_service: DashboardService = await get_dashboard_service(db)

    try:
        # 调用服务层获取趋势数据（服务层会处理查询、过滤、缓存等）
        response_data = await dashboard_service.get_trend_data(
            period=period,
            current_user=current_user
        )
        
        return ResponseBaseSchema.success(data=TrendDataResponse(**response_data))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取趋势数据失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取趋势数据失败：{str(e)}"
        )
