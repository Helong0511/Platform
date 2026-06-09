"""广告主（上游）管理 API 路由模块。

提供广告主 CRUD 接口，业务逻辑委托 AdvertiserService 处理，
路由层仅负责参数校验、权限注入与响应序列化。

路由前缀：/api/v1/cpl/advertisers（由上层 router 挂载）
权限：创建/更新/删除/详情需管理员；列表接口按当前用户数据权限过滤。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_PAGE_SIZE
from app.core.database import get_db
from app.core.dependencies import get_advertiser_service
from app.core.security import get_current_user, require_admin
from app.models.models import User
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.cpl.advertiser import AdvertiserCreate, AdvertiserUpdate, AdvertiserResponse
from app.services.cpl.advertiser_service import AdvertiserService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/",
             response_model=ResponseBaseSchema[AdvertiserResponse],
             summary="创建广告主",
             dependencies=[Depends(require_admin)])
async def create_advertiser(
        advertiser_in: AdvertiserCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    创建广告主（上游）。

    权限：仅管理员。
    请求体：AdvertiserCreate，包含名称、联系方式、上游 Tracklink 等字段。
    业务：委托 AdvertiserService 完成字段校验、唯一性检查、入库及审计日志记录。
    """
    # 使用服务层（业务逻辑在AdvertiserService中）
    advertiser_service: AdvertiserService = await get_advertiser_service(db)

    # 准备广告主数据
    advertiser_data = advertiser_in.model_dump()

    # 调用服务层创建广告主（服务层会处理所有验证和审计日志）
    advertiser = await advertiser_service.create_advertiser(advertiser_data, current_user)

    return ResponseBaseSchema.success(data=AdvertiserResponse.model_validate(advertiser))


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[AdvertiserResponse]],
            summary="获取广告主列表")
async def get_advertisers(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        search: Optional[str] = Query(None, description="搜索关键词（名称、ID）"),
        is_active: Optional[bool] = Query(None, description="是否激活过滤"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    分页获取广告主列表。

    权限：登录用户；非管理员仅能看到有数据权限的广告主。
    筛选：支持关键词搜索（名称/ID）、is_active 状态过滤。
    分页：page、page_size 参数，page_size 上限受 MAX_PAGE_SIZE 约束。
    """
    # 使用服务层（业务逻辑在AdvertiserService中）
    advertiser_service: AdvertiserService = await get_advertiser_service(db)
    advertisers, total = await advertiser_service.get_advertisers(
        current_user=current_user,
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active
    )

    return PaginatedResponseBaseSchema.success(
        data=[AdvertiserResponse.model_validate(adv) for adv in advertisers],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{advertiser_id}",
            response_model=ResponseBaseSchema[AdvertiserResponse],
            summary="获取广告主详情",
            dependencies=[Depends(require_admin)])
async def get_advertiser(
        advertiser_id: int = Path(..., ge=1, description="广告主ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    按 ID 获取单个广告主详情。

    权限：仅管理员。
    路径参数：advertiser_id 为正整数。
    不存在或无权访问时由服务层抛出业务异常。
    """
    # 使用服务层（业务逻辑在AdvertiserService中）
    advertiser_service: AdvertiserService = await get_advertiser_service(db)
    advertiser = await advertiser_service.get_advertiser_by_id(advertiser_id, current_user)

    return ResponseBaseSchema.success(data=AdvertiserResponse.model_validate(advertiser))


@router.put("/{advertiser_id}",
            response_model=ResponseBaseSchema[AdvertiserResponse],
            summary="更新广告主",
            dependencies=[Depends(require_admin)])
async def update_advertiser(
        advertiser_id: int = Path(..., ge=1, description="广告主ID"),
        advertiser_in: AdvertiserUpdate = ...,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    更新广告主信息。

    权限：仅管理员。
    请求体：AdvertiserUpdate，仅提交需变更的字段（exclude_unset）。
    业务：服务层负责字段校验、关联缓存失效及审计日志。
    """
    # 使用服务层（业务逻辑在AdvertiserService中）
    advertiser_service: AdvertiserService = await get_advertiser_service(db)

    # 获取更新数据（排除未设置的字段）
    update_data = advertiser_in.model_dump(exclude_unset=True)

    # 调用服务层更新广告主（服务层会处理所有验证、缓存失效和审计日志）
    advertiser = await advertiser_service.update_advertiser(advertiser_id, update_data, current_user)

    return ResponseBaseSchema.success(data=AdvertiserResponse.model_validate(advertiser))


@router.delete("/{advertiser_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除广告主",
               dependencies=[Depends(require_admin)])
async def delete_advertiser(
        advertiser_id: int = Path(..., ge=1, description="广告主ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    删除广告主。

    权限：仅管理员。
    业务：服务层会检查是否仍有关联 Offer/转化等数据，有关联时拒绝删除。
    成功删除后记录审计日志。
    """
    # 使用服务层（业务逻辑在AdvertiserService中）
    advertiser_service: AdvertiserService = await get_advertiser_service(db)

    # 调用服务层删除广告主（服务层会检查关联数据、记录审计日志）
    await advertiser_service.delete_advertiser(advertiser_id, current_user)

    return ResponseBaseSchema.success(data={"message": "广告主已删除"})
