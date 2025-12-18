"""
渠道管理 API
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.models.models import User, Publisher
from app.schemas.cpl.publisher import PublisherCreate, PublisherUpdate, PublisherResponse
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.core.short_link.generator import generate_unique_short_code

router = APIRouter()
logger = logging.getLogger(__name__)


async def generate_publisher_id(db: AsyncSession) -> str:
    """生成唯一的渠道ID"""
    result = await db.execute(select(Publisher.publisher_id))
    existing_ids = {row[0] for row in result.all()}
    
    publisher_id = generate_unique_short_code(existing_ids, length=6, max_attempts=100)
    if not publisher_id:
        import time
        publisher_id = f"PUB{int(time.time())}"
    
    return publisher_id


@router.post("/",
             response_model=ResponseBaseSchema[PublisherResponse],
             summary="创建渠道",
             dependencies=[Depends(require_admin)])
async def create_publisher(
    publisher_in: PublisherCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建渠道（仅管理员）"""
    publisher_id = await generate_publisher_id(db)
    
    publisher = Publisher(
        publisher_id=publisher_id,
        publisher_name=publisher_in.publisher_name,
        email=publisher_in.email,
        price_discount=publisher_in.price_discount,
        is_active=publisher_in.is_active
    )
    
    try:
        db.add(publisher)
        await db.commit()
        await db.refresh(publisher)
        
        logger.info(f"渠道创建成功: {publisher_id}")
        return ResponseBaseSchema.success(data=PublisherResponse.model_validate(publisher))
    except Exception as e:
        await db.rollback()
        logger.error(f"创建渠道失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建渠道失败: {str(e)}"
        )


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[PublisherResponse]],
            summary="获取渠道列表",
            dependencies=[Depends(require_admin)])
async def get_publishers(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    search: Optional[str] = Query(None, description="搜索关键词（名称、ID）"),
    is_active: Optional[bool] = Query(None, description="是否激活过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取渠道列表（仅管理员）"""
    query = select(Publisher)
    
    if search:
        query = query.where(
            (Publisher.publisher_name.like(f"%{search}%")) |
            (Publisher.publisher_id.like(f"%{search}%"))
        )
    
    if is_active is not None:
        query = query.where(Publisher.is_active == is_active)
    
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    
    query = query.order_by(Publisher.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    publishers = result.scalars().all()
    
    return PaginatedResponseBaseSchema.success(
        data=[PublisherResponse.model_validate(pub) for pub in publishers],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{publisher_id}",
            response_model=ResponseBaseSchema[PublisherResponse],
            summary="获取渠道详情",
            dependencies=[Depends(require_admin)])
async def get_publisher(
    publisher_id: int = Path(..., ge=1, description="渠道ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取渠道详情（仅管理员）"""
    result = await db.execute(
        select(Publisher).where(Publisher.id == publisher_id)
    )
    publisher = result.scalars().first()
    
    if not publisher:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"渠道ID {publisher_id} 不存在"
        )
    
    return ResponseBaseSchema.success(data=PublisherResponse.model_validate(publisher))


@router.put("/{publisher_id}",
            response_model=ResponseBaseSchema[PublisherResponse],
            summary="更新渠道",
            dependencies=[Depends(require_admin)])
async def update_publisher(
    publisher_id: int = Path(..., ge=1, description="渠道ID"),
    publisher_in: PublisherUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新渠道（仅管理员）"""
    result = await db.execute(
        select(Publisher).where(Publisher.id == publisher_id)
    )
    publisher = result.scalars().first()
    
    if not publisher:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"渠道ID {publisher_id} 不存在"
        )
    
    update_data = publisher_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(publisher, key, value)
    
    try:
        await db.commit()
        await db.refresh(publisher)
        
        logger.info(f"渠道更新成功: {publisher.publisher_id}")
        return ResponseBaseSchema.success(data=PublisherResponse.model_validate(publisher))
    except Exception as e:
        await db.rollback()
        logger.error(f"更新渠道失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新渠道失败: {str(e)}"
        )


@router.delete("/{publisher_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除渠道",
               dependencies=[Depends(require_admin)])
async def delete_publisher(
    publisher_id: int = Path(..., ge=1, description="渠道ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除渠道（仅管理员）"""
    result = await db.execute(
        select(Publisher).where(Publisher.id == publisher_id)
    )
    publisher = result.scalars().first()
    
    if not publisher:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"渠道ID {publisher_id} 不存在"
        )
    
    try:
        from sqlalchemy import delete
        await db.execute(delete(Publisher).where(Publisher.id == publisher_id))
        await db.commit()
        
        logger.info(f"渠道删除成功: {publisher.publisher_id}")
        return ResponseBaseSchema.success(data={"message": "渠道已删除"})
    except Exception as e:
        await db.rollback()
        logger.error(f"删除渠道失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除渠道失败: {str(e)}"
        )

