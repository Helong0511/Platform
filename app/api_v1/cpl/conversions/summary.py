"""转化总览统计 API 路由模块。

按时间范围、Offer、渠道等维度聚合转化数量与金额，
供管理端仪表盘与转化汇总页展示。业务逻辑委托 ConversionService。

路由前缀：/api/v1/cpl/conversions/summary
权限：已登录用户（按数据权限过滤可见范围）。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_readonly
from app.core.dependencies import get_conversion_service
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import get_current_user, require_publisher_or_admin
from app.models.models import User
from app.schemas.base import ResponseBaseSchema
from app.services.cpl.conversion_service import ConversionService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/",
            response_model=ResponseBaseSchema[dict],
            summary="获取转化总览统计",
            dependencies=[Depends(require_publisher_or_admin)])
async def get_conversion_summary(
        start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
        publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
        advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
        db: AsyncSession = Depends(get_db_readonly),
        current_user: User = Depends(get_current_user)
):
    """
    获取转化总览统计（已重构使用服务层，批量加载关联数据）
    按Offer和Publisher分组统计，返回：
    - Offer ID
    - Offer Name
    - Advertiser（仅管理员可见）
    - Publisher
    - Click: 点击数量
    - Conversion: 转化数量
    - CR (Conversion Rate): 转化率 = Conversion / Click
    - PO: 总支付金额（仅管理员可见）
    - PO（扣价后）: 扣价后的总支付金额（所有用户可见）
    
    客户登录时，只显示该客户关联的渠道的转化数据
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        # 使用服务层（业务逻辑在ConversionService中，已优化批量加载）

        conversion_service: ConversionService = await get_conversion_service(db)

        # 调用服务层获取转化总览（服务层会处理权限过滤和批量加载）
        summary = await conversion_service.get_conversion_summary(
            current_user=current_user,
            start_date=start_date,
            end_date=end_date,
            offer_id=offer_id,
            publisher_id=publisher_id,
            advertiser_id=advertiser_id
        )

        # 服务层已返回完整的统计数据（包括总点击数、总转化率等）
        return ResponseBaseSchema.success(data=summary)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取转化总览统计失败：error_type=%s", type(e).__name__)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail="获取转化总览统计失败，请稍后重试",
        )


@router.get("/by-offer",
            response_model=ResponseBaseSchema[list],
            summary="按Offer统计",
            dependencies=[Depends(require_publisher_or_admin)])
async def get_summary_by_offer(
        start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        db: AsyncSession = Depends(get_db_readonly),
        current_user: User = Depends(get_current_user)
):
    """
    按Offer统计转化数据（已重构使用服务层，批量查询优化）
    
    客户登录时，只显示该客户关联的渠道的转化数据
    
    功能：查询单条或详情（get_summary_by_offer）。
    实现：异步端点，通过 Service 层访问数据库/缓存。
    鉴权：由 Depends(get_current_user) 或 require_admin 控制访问范围。
    响应：统一 ResponseBaseSchema / PaginatedResponseBaseSchema 包装。
    """
    try:
        # 使用服务层（业务逻辑在ConversionService中，已优化批量查询）
        conversion_service: ConversionService = await get_conversion_service(db)

        # 调用服务层获取按Offer的统计
        stats_list = await conversion_service.get_conversions_by_offer(
            current_user=current_user,
            start_date=start_date,
            end_date=end_date
        )

        return ResponseBaseSchema.success(data=stats_list)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("按 Offer 统计失败：error_type=%s", type(e).__name__)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail="按 Offer 统计失败，请稍后重试",
        )
