"""短链接点击访问记录 API 路由模块。

提供 clicks 表数据的分页查询与详情查看，支持按 click_id、Offer、
渠道、时间范围等维度筛选。业务逻辑委托 ClickService 处理。

路由前缀：/api/v1/cpl/clicks
权限：所有端点需管理员。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_PAGE_SIZE
from app.core.audit_log import log_user_action, commit_audit_log
from app.core.database import get_db
from app.core.dependencies import get_click_service
from app.core.security import get_current_user, require_admin
from app.models.models import User
from app.schemas.base import PaginatedResponseBaseSchema, ResponseBaseSchema
from app.services.click_service import ClickService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list],
            summary="获取短链接访问记录列表",
            dependencies=[Depends(require_admin)])
async def get_clicks(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        click_id: Optional[str] = Query(None, description="Click ID过滤"),
        conversion_id: Optional[str] = Query(None, description="转化ID过滤"),
        offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
        publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
        advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
        short_link_id: Optional[int] = Query(None, description="短链接ID过滤"),
        ip: Optional[str] = Query(None, description="IP地址过滤"),
        country: Optional[str] = Query(None, description="国家过滤"),
        start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    获取短链接访问记录列表（clicks 表数据，已重构使用服务层）
    仅管理员可访问
    
    优化说明：
    - 如果没有提供日期范围，默认查询最近7天的数据（优化性能）
    - 最大查询范围限制为90天（防止查询过大数据量）
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 使用服务层（业务逻辑在ClickService中）
    click_service: ClickService = await get_click_service(db)

    # ---------- 异常处理 ----------
    try:
        # 调用服务层获取点击记录列表（服务层会处理查询、过滤、分页、日期验证等）
        click_list, total = await click_service.get_clicks(
            page=page,
            page_size=page_size,
            click_id=click_id,
            conversion_id=conversion_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
            advertiser_id=advertiser_id,
            short_link_id=short_link_id,
            ip=ip,
            country=country,
            start_date=start_date,
            end_date=end_date
        )

        return PaginatedResponseBaseSchema.success(
            data=click_list,
            total=total,
            page=page,
            page_size=page_size
        )
    except Exception as e:
        logger.error("获取短链接访问记录列表失败: error_type=%s", type(e).__name__)
        raise


@router.get("/{click_record_id}",
            response_model=ResponseBaseSchema[dict],
            summary="获取短链接访问记录详情",
            dependencies=[Depends(require_admin)])
async def get_click_detail(
        click_record_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    获取单条短链接点击记录详情。

    权限：登录用户。
    返回完整请求头、设备信息、归因参数等调试字段。
    """
    click_service: ClickService = await get_click_service(db)

    try:
        click_detail = await click_service.get_click_detail(click_record_id)
        return ResponseBaseSchema.success(data=click_detail)
    except Exception as e:
        logger.error("获取短链接访问记录详情失败: id=%s error_type=%s", click_record_id, type(e).__name__)
        raise


@router.post(
    "/{click_record_id}/facebook-report",
    response_model=ResponseBaseSchema[dict],
    summary="手动补报 Facebook 像素",
    dependencies=[Depends(require_admin)]
)
async def resend_click_facebook_report(
        request: Request,
        click_record_id: int = Path(..., ge=1),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    对已归因转化的点击补发 Facebook Pixel/CAPI 上报。

    权限：仅管理员。
    用于修复漏报或测试斗篷上报链路。
    """
    click_service: ClickService = await get_click_service(db)
    try:
        result = await click_service.resend_facebook_report(click_record_id)
        await log_user_action(
            db=db,
            action_type="TASK_RUN",
            user=current_user,
            resource_type="CLICK",
            resource_id=click_record_id,
            resource_name=f"Facebook像素补报-{click_record_id}",
            request=request,
        )
        await commit_audit_log(db)
        return ResponseBaseSchema.success(
            data=result,
            message="Facebook 像素补报已发送"
        )
    except Exception as e:
        logger.error(
            "Facebook 像素补报失败: click_record_id=%s user=%s error=%s",
            click_record_id,
            current_user.username,
            str(e),
            exc_info=True
        )
        raise
