"""
渠道管理 API
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, String

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.constants import MAX_PAGE_SIZE
from app.core.validation import validate_postback_url_placeholders
from app.models.models import User, Publisher, Client
from sqlalchemy.orm import joinedload
from app.schemas.cpl.publisher import PublisherCreate, PublisherUpdate, PublisherResponse
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema

router = APIRouter()
logger = logging.getLogger(__name__)


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
    # 验证 Postback URL 中的占位符
    if publisher_in.postback_url:
        is_valid, error_msg = validate_postback_url_placeholders(publisher_in.postback_url)
        if not is_valid:
            raise_api_exception(
                ErrorCode.INVALID_INPUT,
                detail=error_msg
            )
    
    publisher = Publisher(
        publisher_name=publisher_in.publisher_name,
        email=publisher_in.email,
        price_discount=publisher_in.price_discount,
        postback_url=publisher_in.postback_url,
        postback_method=publisher_in.postback_method,
        client_id=publisher_in.client_id,
        is_active=publisher_in.is_active
    )
    
    try:
        db.add(publisher)
        await db.commit()
        await db.refresh(publisher)
        
        # 获取客户信息（用户的 full_name）
        client_name = None
        if publisher.client_id:
            client_result = await db.execute(
                select(Client).options(joinedload(Client.user)).where(Client.id == publisher.client_id)
            )
            client = client_result.scalars().first()
            if client and client.user:
                client_name = client.user.full_name or client.company_name
        
        publisher_data = PublisherResponse.model_validate(publisher)
        publisher_data.client_name = client_name
        
        logger.info(f"渠道创建成功: id={publisher.id}")
        return ResponseBaseSchema.success(data=publisher_data)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建渠道失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建渠道失败: {str(e)}"
        )


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[PublisherResponse]],
            summary="获取渠道列表")
async def get_publishers(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    search: Optional[str] = Query(None, description="搜索关键词（名称、ID）"),
    is_active: Optional[bool] = Query(None, description="是否激活过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取渠道列表（所有登录用户可访问）"""
    query = select(Publisher)
    
    if search:
        query = query.where(
            (Publisher.publisher_name.like(f"%{search}%")) |
            (Publisher.id.cast(String).like(f"%{search}%"))
        )
    
    if is_active is not None:
        query = query.where(Publisher.is_active == is_active)
    
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    
    query = query.order_by(Publisher.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    publishers = result.scalars().all()
    
    # 获取所有客户信息（用户的 full_name）
    client_ids = [pub.client_id for pub in publishers if pub.client_id]
    clients_dict = {}
    if client_ids:
        clients_result = await db.execute(
            select(Client).options(joinedload(Client.user)).where(Client.id.in_(client_ids))
        )
        clients = clients_result.scalars().all()
        clients_dict = {
            client.id: (client.user.full_name if client.user and client.user.full_name else client.company_name)
            for client in clients
        }
    
    # 构建响应数据
    publishers_data = []
    for pub in publishers:
        pub_data = PublisherResponse.model_validate(pub)
        pub_data.client_name = clients_dict.get(pub.client_id) if pub.client_id else None
        publishers_data.append(pub_data)
    
    return PaginatedResponseBaseSchema.success(
        data=publishers_data,
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
    
    # 获取客户信息（用户的 full_name）
    client_name = None
    if publisher.client_id:
        client_result = await db.execute(
            select(Client).options(joinedload(Client.user)).where(Client.id == publisher.client_id)
        )
        client = client_result.scalars().first()
        if client and client.user:
            client_name = client.user.full_name or client.company_name
    
    publisher_data = PublisherResponse.model_validate(publisher)
    publisher_data.client_name = client_name
    
    return ResponseBaseSchema.success(data=publisher_data)


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
    # 验证 Postback URL 中的占位符（如果提供了 postback_url）
    if publisher_in.postback_url is not None:
        is_valid, error_msg = validate_postback_url_placeholders(publisher_in.postback_url)
        if not is_valid:
            raise_api_exception(
                ErrorCode.INVALID_INPUT,
                detail=error_msg
            )
    
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
        
        # 获取客户信息（用户的 full_name）
        client_name = None
        if publisher.client_id:
            client_result = await db.execute(
                select(Client).options(joinedload(Client.user)).where(Client.id == publisher.client_id)
            )
            client = client_result.scalars().first()
            if client and client.user:
                client_name = client.user.full_name or client.company_name
        
        publisher_data = PublisherResponse.model_validate(publisher)
        publisher_data.client_name = client_name
        
        logger.info(f"渠道更新成功: id={publisher.id}")
        return ResponseBaseSchema.success(data=publisher_data)
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
        
        logger.info(f"渠道删除成功: id={publisher.id}")
        return ResponseBaseSchema.success(data={"message": "渠道已删除"})
    except Exception as e:
        await db.rollback()
        logger.error(f"删除渠道失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除渠道失败: {str(e)}"
        )

