"""
广告主管理 API
"""
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.models.models import User, UserRole, Advertiser
from app.schemas.cpl.advertiser import AdvertiserCreate, AdvertiserUpdate, AdvertiserResponse
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.core.short_link.generator import generate_unique_short_code

router = APIRouter()
logger = logging.getLogger(__name__)


async def generate_advertiser_id(db: AsyncSession) -> str:
    """生成唯一的广告主ID"""
    # 获取所有已存在的 advertiser_id
    result = await db.execute(select(Advertiser.advertiser_id))
    existing_ids = {row[0] for row in result.all()}
    
    # 生成唯一ID（6位）
    advertiser_id = generate_unique_short_code(existing_ids, length=6, max_attempts=100)
    if not advertiser_id:
        # 如果生成失败，使用时间戳
        import time
        advertiser_id = f"ADV{int(time.time())}"
    
    return advertiser_id


@router.post("/",
             response_model=ResponseBaseSchema[AdvertiserResponse],
             summary="创建广告主",
             dependencies=[Depends(require_admin)])
async def create_advertiser(
    advertiser_in: AdvertiserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建广告主（仅管理员）"""
    # 生成唯一的 advertiser_id
    advertiser_id = await generate_advertiser_id(db)
    
    advertiser = Advertiser(
        advertiser_id=advertiser_id,
        advertiser_name=advertiser_in.advertiser_name,
        email=advertiser_in.email,
        mobile=advertiser_in.mobile,
        is_active=advertiser_in.is_active
    )
    
    try:
        db.add(advertiser)
        await db.commit()
        await db.refresh(advertiser)
        
        logger.info(f"广告主创建成功: {advertiser_id}")
        return ResponseBaseSchema.success(data=AdvertiserResponse.model_validate(advertiser))
    except Exception as e:
        await db.rollback()
        logger.error(f"创建广告主失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建广告主失败: {str(e)}"
        )


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[AdvertiserResponse]],
            summary="获取广告主列表",
            dependencies=[Depends(require_admin)])
async def get_advertisers(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    search: Optional[str] = Query(None, description="搜索关键词（名称、ID）"),
    is_active: Optional[bool] = Query(None, description="是否激活过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取广告主列表（仅管理员）"""
    query = select(Advertiser)
    
    # 搜索过滤
    if search:
        query = query.where(
            (Advertiser.advertiser_name.like(f"%{search}%")) |
            (Advertiser.advertiser_id.like(f"%{search}%"))
        )
    
    # 激活状态过滤
    if is_active is not None:
        query = query.where(Advertiser.is_active == is_active)
    
    # 总数
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    
    # 分页
    query = query.order_by(Advertiser.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    advertisers = result.scalars().all()
    
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
    """获取广告主详情（仅管理员）"""
    result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = result.scalars().first()
    
    if not advertiser:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"广告主ID {advertiser_id} 不存在"
        )
    
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
    """更新广告主（仅管理员）"""
    result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = result.scalars().first()
    
    if not advertiser:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"广告主ID {advertiser_id} 不存在"
        )
    
    # 更新字段
    update_data = advertiser_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(advertiser, key, value)
    
    try:
        await db.commit()
        await db.refresh(advertiser)
        
        logger.info(f"广告主更新成功: {advertiser.advertiser_id}")
        return ResponseBaseSchema.success(data=AdvertiserResponse.model_validate(advertiser))
    except Exception as e:
        await db.rollback()
        logger.error(f"更新广告主失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新广告主失败: {str(e)}"
        )


@router.delete("/{advertiser_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除广告主",
               dependencies=[Depends(require_admin)])
async def delete_advertiser(
    advertiser_id: int = Path(..., ge=1, description="广告主ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除广告主（仅管理员）"""
    result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = result.scalars().first()
    
    if not advertiser:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"广告主ID {advertiser_id} 不存在"
        )
    
    try:
        from sqlalchemy import delete
        await db.execute(delete(Advertiser).where(Advertiser.id == advertiser_id))
        await db.commit()
        
        logger.info(f"广告主删除成功: {advertiser.advertiser_id}")
        return ResponseBaseSchema.success(data={"message": "广告主已删除"})
    except Exception as e:
        await db.rollback()
        logger.error(f"删除广告主失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除广告主失败: {str(e)}"
        )

