"""
通知配置管理API端点
提供客户和产品通知配置的CRUD操作，以及通知记录的查询
"""
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_, func, delete

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.utils import parse_date_to_app_timezone
from app.models.models import (
    Client, Product, User, UserRole,
    ClientNotificationConfig, ProductNotificationConfig, PostbackNotification
)
from app.schemas.notification import (
    ClientNotificationConfigCreate,
    ClientNotificationConfigUpdate,
    ClientNotificationConfigResponse,
    ProductNotificationConfigCreate,
    ProductNotificationConfigUpdate,
    ProductNotificationConfigResponse,
    PostbackNotificationResponse,
    PostbackNotificationListResponse
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema

# 创建路由实例
router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== 客户通知配置 ====================

@router.get("/clients/{client_id}/config", 
            response_model=ResponseBaseSchema[ClientNotificationConfigResponse],
            summary="获取客户通知配置")
async def get_client_notification_config(
    client_id: int = Path(..., ge=1, description="客户ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取客户的通知配置"""
    # 权限检查：管理员或客户本人
    if current_user.role != UserRole.ADMIN:
        if not current_user.client_id or current_user.client_id != client_id:
            raise_api_exception(
                ErrorCode.ACCESS_DENIED,
                detail="无权访问该客户的通知配置"
            )
    
    # 验证客户是否存在
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalars().first()
    if not client:
        raise_api_exception(
            ErrorCode.CLIENT_NOT_FOUND,
            detail=f"客户ID {client_id} 不存在"
        )
    
    # 获取配置
    result = await db.execute(
        select(ClientNotificationConfig).where(ClientNotificationConfig.client_id == client_id)
    )
    config = result.scalars().first()
    
    if not config:
        # 如果不存在，返回默认配置
        return ResponseBaseSchema.success(data=ClientNotificationConfigResponse(
            id=0,
            client_id=client_id,
            notification_enabled=True,
            notify_on_conversion=True,
            notify_on_high_value=False,
            high_value_threshold=None,
            notify_channels=None,
            telegram_chat_id=None,
            email_address=None,
            phone_number=None,
            notification_frequency="realtime",
            created_at=None,
            updated_at=None
        ))
    
    return ResponseBaseSchema.success(data=ClientNotificationConfigResponse.model_validate(config))


@router.post("/clients/{client_id}/config",
             response_model=ResponseBaseSchema[ClientNotificationConfigResponse],
             summary="创建或更新客户通知配置")
async def create_or_update_client_notification_config(
    request: Request,
    client_id: int = Path(..., ge=1, description="客户ID"),
    config_in: ClientNotificationConfigUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """创建或更新客户的通知配置（仅管理员）"""
    # 验证客户是否存在
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalars().first()
    if not client:
        raise_api_exception(
            ErrorCode.CLIENT_NOT_FOUND,
            detail=f"客户ID {client_id} 不存在"
        )
    
    # 检查是否已存在配置
    result = await db.execute(
        select(ClientNotificationConfig).where(ClientNotificationConfig.client_id == client_id)
    )
    existing_config = result.scalars().first()
    
    if existing_config:
        # 更新现有配置
        update_data = config_in.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(existing_config, key, value)
        
        try:
            await db.commit()
            await db.refresh(existing_config)
            logger.info(f"客户 {client_id} 的通知配置已更新")
            return ResponseBaseSchema.success(data=ClientNotificationConfigResponse.model_validate(existing_config))
        except Exception as e:
            await db.rollback()
            logger.error(f"更新客户通知配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新客户通知配置失败: {str(e)}"
            )
    else:
        # 创建新配置
        new_config = ClientNotificationConfig(
            client_id=client_id,
            **config_in.model_dump()
        )
        
        try:
            db.add(new_config)
            await db.commit()
            await db.refresh(new_config)
            logger.info(f"客户 {client_id} 的通知配置已创建")
            return ResponseBaseSchema.success(data=ClientNotificationConfigResponse.model_validate(new_config))
        except Exception as e:
            await db.rollback()
            logger.error(f"创建客户通知配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"创建客户通知配置失败: {str(e)}"
            )


@router.delete("/clients/{client_id}/config",
               response_model=ResponseBaseSchema[dict],
               summary="删除客户通知配置")
async def delete_client_notification_config(
    client_id: int = Path(..., ge=1, description="客户ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """删除客户的通知配置（仅管理员）"""
    result = await db.execute(
        select(ClientNotificationConfig).where(ClientNotificationConfig.client_id == client_id)
    )
    config = result.scalars().first()
    
    if not config:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"客户ID {client_id} 的通知配置不存在"
        )
    
    try:
        await db.execute(delete(ClientNotificationConfig).where(ClientNotificationConfig.id == config.id))
        await db.commit()
        logger.info(f"客户 {client_id} 的通知配置已删除")
        return ResponseBaseSchema.success(data={"message": "通知配置已删除"})
    except Exception as e:
        await db.rollback()
        logger.error(f"删除客户通知配置失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除客户通知配置失败: {str(e)}"
        )


# ==================== 产品通知配置 ====================

@router.get("/products/{product_id}/config",
            response_model=ResponseBaseSchema[ProductNotificationConfigResponse],
            summary="获取产品通知配置")
async def get_product_notification_config(
    product_id: int = Path(..., ge=1, description="产品ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取产品的通知配置"""
    # 验证产品是否存在
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()
    if not product:
        raise_api_exception(
            ErrorCode.PRODUCT_NOT_FOUND,
            detail=f"产品ID {product_id} 不存在"
        )
    
    # 权限检查：管理员或产品所属客户
    if current_user.role != UserRole.ADMIN:
        if not current_user.client_id or current_user.client_id != product.client_id:
            raise_api_exception(
                ErrorCode.ACCESS_DENIED,
                detail="无权访问该产品的通知配置"
            )
    
    # 获取配置
    result = await db.execute(
        select(ProductNotificationConfig).where(ProductNotificationConfig.product_id == product_id)
    )
    config = result.scalars().first()
    
    if not config:
        # 如果不存在，返回默认配置
        return ResponseBaseSchema.success(data=ProductNotificationConfigResponse(
            id=0,
            product_id=product_id,
            notification_enabled=True,
            notify_on_conversion=True,
            notify_on_high_value=False,
            high_value_threshold=None,
            notify_channels=None,
            telegram_chat_id=None,
            email_address=None,
            phone_number=None,
            notification_frequency="realtime",
            created_at=None,
            updated_at=None
        ))
    
    return ResponseBaseSchema.success(data=ProductNotificationConfigResponse.model_validate(config))


@router.post("/products/{product_id}/config",
             response_model=ResponseBaseSchema[ProductNotificationConfigResponse],
             summary="创建或更新产品通知配置")
async def create_or_update_product_notification_config(
    request: Request,
    product_id: int = Path(..., ge=1, description="产品ID"),
    config_in: ProductNotificationConfigUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """创建或更新产品的通知配置（仅管理员）"""
    # 验证产品是否存在
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()
    if not product:
        raise_api_exception(
            ErrorCode.PRODUCT_NOT_FOUND,
            detail=f"产品ID {product_id} 不存在"
        )
    
    # 检查是否已存在配置
    result = await db.execute(
        select(ProductNotificationConfig).where(ProductNotificationConfig.product_id == product_id)
    )
    existing_config = result.scalars().first()
    
    if existing_config:
        # 更新现有配置
        update_data = config_in.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(existing_config, key, value)
        
        try:
            await db.commit()
            await db.refresh(existing_config)
            logger.info(f"产品 {product_id} 的通知配置已更新")
            return ResponseBaseSchema.success(data=ProductNotificationConfigResponse.model_validate(existing_config))
        except Exception as e:
            await db.rollback()
            logger.error(f"更新产品通知配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新产品通知配置失败: {str(e)}"
            )
    else:
        # 创建新配置
        new_config = ProductNotificationConfig(
            product_id=product_id,
            **config_in.model_dump()
        )
        
        try:
            db.add(new_config)
            await db.commit()
            await db.refresh(new_config)
            logger.info(f"产品 {product_id} 的通知配置已创建")
            return ResponseBaseSchema.success(data=ProductNotificationConfigResponse.model_validate(new_config))
        except Exception as e:
            await db.rollback()
            logger.error(f"创建产品通知配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"创建产品通知配置失败: {str(e)}"
            )


@router.delete("/products/{product_id}/config",
               response_model=ResponseBaseSchema[dict],
               summary="删除产品通知配置")
async def delete_product_notification_config(
    product_id: int = Path(..., ge=1, description="产品ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """删除产品的通知配置（仅管理员）"""
    result = await db.execute(
        select(ProductNotificationConfig).where(ProductNotificationConfig.product_id == product_id)
    )
    config = result.scalars().first()
    
    if not config:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"产品ID {product_id} 的通知配置不存在"
        )
    
    try:
        await db.execute(delete(ProductNotificationConfig).where(ProductNotificationConfig.id == config.id))
        await db.commit()
        logger.info(f"产品 {product_id} 的通知配置已删除")
        return ResponseBaseSchema.success(data={"message": "通知配置已删除"})
    except Exception as e:
        await db.rollback()
        logger.error(f"删除产品通知配置失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除产品通知配置失败: {str(e)}"
        )


# ==================== 通知记录查询 ====================

@router.get("/notifications",
            response_model=PaginatedResponseBaseSchema[list[PostbackNotificationResponse]],
            summary="获取通知记录列表")
async def get_notification_records(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    client_id: Optional[int] = Query(None, description="客户ID过滤"),
    product_id: Optional[int] = Query(None, description="产品ID过滤"),
    notification_status: Optional[str] = Query(None, description="通知状态过滤（sent, failed, pending）"),
    notification_channel: Optional[str] = Query(None, description="通知渠道过滤（telegram, email, sms）"),
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取通知记录列表（支持分页和过滤）"""
    # 权限检查：管理员可以查看所有，客户只能查看自己的
    query = select(PostbackNotification)
    
    if current_user.role != UserRole.ADMIN:
        # 客户只能查看自己客户的通知记录
        if not current_user.client_id:
            return PaginatedResponseBaseSchema.success(
                data=[],
                total=0,
                page=page,
                page_size=page_size
            )
        query = query.where(PostbackNotification.client_id == current_user.client_id)
    
    # 应用过滤条件
    conditions = []
    
    if client_id:
        conditions.append(PostbackNotification.client_id == client_id)
    
    if product_id:
        conditions.append(PostbackNotification.product_id == product_id)
    
    if notification_status:
        conditions.append(PostbackNotification.notification_status == notification_status)
    
    if notification_channel:
        conditions.append(PostbackNotification.notification_channel == notification_channel)
    
    if start_date:
        try:
            start_dt = parse_date_to_app_timezone(start_date, is_end_date=False)
            conditions.append(PostbackNotification.created_at >= start_dt)
        except ValueError:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="开始日期格式错误，应为 YYYY-MM-DD"
            )
    
    if end_date:
        try:
            end_dt = parse_date_to_app_timezone(end_date, is_end_date=True)
            conditions.append(PostbackNotification.created_at <= end_dt)
        except ValueError:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="结束日期格式错误，应为 YYYY-MM-DD"
            )
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # 排序：最新的在前
    query = query.order_by(PostbackNotification.created_at.desc())
    
    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    # 执行查询
    result = await db.execute(query)
    notifications = result.scalars().all()
    
    return PaginatedResponseBaseSchema.success(
        data=[PostbackNotificationResponse.model_validate(n) for n in notifications],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/notifications/{notification_id}",
            response_model=ResponseBaseSchema[PostbackNotificationResponse],
            summary="获取通知记录详情")
async def get_notification_record(
    notification_id: int = Path(..., ge=1, description="通知记录ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取通知记录详情"""
    result = await db.execute(
        select(PostbackNotification).where(PostbackNotification.id == notification_id)
    )
    notification = result.scalars().first()
    
    if not notification:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"通知记录ID {notification_id} 不存在"
        )
    
    # 权限检查
    if current_user.role != UserRole.ADMIN:
        if not current_user.client_id or notification.client_id != current_user.client_id:
            raise_api_exception(
                ErrorCode.ACCESS_DENIED,
                detail="无权访问该通知记录"
            )
    
    return ResponseBaseSchema.success(data=PostbackNotificationResponse.model_validate(notification))

