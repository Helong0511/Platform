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
from app.core.dependencies import get_publisher_service
from app.services.cpl.publisher_service import PublisherService
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
    """创建渠道（已重构使用服务层）"""
    # 使用服务层（业务逻辑在PublisherService中）
    publisher_service: PublisherService = await get_publisher_service(db)
    
    # 准备渠道数据
    publisher_data = publisher_in.model_dump()
    
    # 调用服务层创建渠道（服务层会处理验证和审计日志）
    publisher = await publisher_service.create_publisher(publisher_data, current_user)
    
    # 获取客户信息（用户的 full_name）
    client_name = None
    if publisher.client_id:
        # 重新加载以获取客户信息
        publisher = await publisher_service.get_publisher_by_id(publisher.id, current_user, include_client=True)
        if publisher.client and publisher.client.user:
            client_name = publisher.client.user.full_name or publisher.client.company_name
        elif publisher.client:
            client_name = publisher.client.company_name
    
    publisher_response = PublisherResponse.model_validate(publisher)
    publisher_response.client_name = client_name
    
    return ResponseBaseSchema.success(data=publisher_response)


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
    """获取渠道列表（已重构使用服务层，批量加载客户信息）"""
    # 使用服务层（业务逻辑在PublisherService中，已优化批量加载）
    publisher_service: PublisherService = await get_publisher_service(db)
    publishers, total = await publisher_service.get_publishers(
        current_user=current_user,
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active
    )
    
    # 构建响应数据（客户信息已通过selectinload预加载）
    publishers_data = []
    for pub in publishers:
        pub_data = PublisherResponse.model_validate(pub)
        # 客户信息已预加载
        if pub.client and pub.client.user:
            pub_data.client_name = pub.client.user.full_name if pub.client.user.full_name else pub.client.company_name
        elif pub.client:
            pub_data.client_name = pub.client.company_name
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
    """获取渠道详情（已重构使用服务层）"""
    # 使用服务层（业务逻辑在PublisherService中）
    publisher_service: PublisherService = await get_publisher_service(db)
    
    # 获取渠道（包含客户信息）
    publisher = await publisher_service.get_publisher_by_id(publisher_id, current_user, include_client=True)
    
    # 获取客户信息（用户的 full_name）
    client_name = None
    if publisher.client and publisher.client.user:
        client_name = publisher.client.user.full_name or publisher.client.company_name
    elif publisher.client:
        client_name = publisher.client.company_name
    
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
    """更新渠道（已重构使用服务层）"""
    # 使用服务层（业务逻辑在PublisherService中）
    publisher_service: PublisherService = await get_publisher_service(db)
    
    # 获取更新数据（排除未设置的字段）
    update_data = publisher_in.model_dump(exclude_unset=True)
    
    # 调用服务层更新渠道（服务层会处理验证、缓存失效和审计日志）
    publisher = await publisher_service.update_publisher(publisher_id, update_data, current_user)
    
    # 获取客户信息（用户的 full_name）
    client_name = None
    if publisher.client_id:
        # 重新加载以获取客户信息
        publisher = await publisher_service.get_publisher_by_id(publisher.id, current_user, include_client=True)
        if publisher.client and publisher.client.user:
            client_name = publisher.client.user.full_name or publisher.client.company_name
        elif publisher.client:
            client_name = publisher.client.company_name
    
    publisher_data = PublisherResponse.model_validate(publisher)
    publisher_data.client_name = client_name
    
    return ResponseBaseSchema.success(data=publisher_data)


@router.delete("/{publisher_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除渠道",
               dependencies=[Depends(require_admin)])
async def delete_publisher(
    publisher_id: int = Path(..., ge=1, description="渠道ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除渠道（已重构使用服务层）"""
    # 使用服务层（业务逻辑在PublisherService中）
    publisher_service: PublisherService = await get_publisher_service(db)
    
    # 调用服务层删除渠道（服务层会检查关联数据、记录审计日志）
    await publisher_service.delete_publisher(publisher_id, current_user)
    
    return ResponseBaseSchema.success(data={"message": "渠道已删除"})

