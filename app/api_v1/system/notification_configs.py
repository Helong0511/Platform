"""
通知配置管理API端点
提供客户和产品通知配置的CRUD操作，以及通知记录的查询
"""
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_, func, delete

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.constants import MAX_PAGE_SIZE
from app.core.utils import parse_date_to_app_timezone, get_app_now_naive
from app.core.dependencies import get_notification_config_service
from app.core.telegram import send_telegram_message_async
from app.models.models import (
    Client, Product, User, UserRole,
    ClientNotificationConfig, ProductNotificationConfig, AdminNotificationConfig,
    PostbackNotification, PostbackConversion
)
from app.schemas.notification import (
    ClientNotificationConfigCreate,
    ClientNotificationConfigUpdate,
    ClientNotificationConfigResponse,
    ProductNotificationConfigCreate,
    ProductNotificationConfigUpdate,
    ProductNotificationConfigResponse,
    AdminNotificationConfigCreate,
    AdminNotificationConfigUpdate,
    AdminNotificationConfigResponse,
    TestConnectionRequest,
    TestMessageRequest,
    PostbackNotificationResponse,
    PostbackNotificationListResponse
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.services.notification_config_service import NotificationConfigService
from app.services.telegram_notification_service import TelegramNotificationService

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
    """获取客户的通知配置（已重构使用服务层）"""
    # 使用服务层（业务逻辑在NotificationConfigService中）
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    
    # 调用服务层获取客户通知配置（服务层会处理权限检查和验证）
    config = await notification_service.get_client_notification_config(client_id, current_user)
    
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
    """创建或更新客户的通知配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在NotificationConfigService中）
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    
    # 准备配置数据
    config_data = config_in.model_dump(exclude_unset=True)
    
    # 调用服务层创建或更新客户通知配置（服务层会处理验证和逻辑）
    config = await notification_service.create_or_update_client_notification_config(
        client_id, config_data, current_user
    )
    
    return ResponseBaseSchema.success(data=ClientNotificationConfigResponse.model_validate(config))


@router.delete("/clients/{client_id}/config",
               response_model=ResponseBaseSchema[dict],
               summary="删除客户通知配置")
async def delete_client_notification_config(
    client_id: int = Path(..., ge=1, description="客户ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """删除客户的通知配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在NotificationConfigService中）
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    
    # 调用服务层删除客户通知配置（服务层会处理验证和删除）
    await notification_service.delete_client_notification_config(client_id, current_user)
    
    return ResponseBaseSchema.success(data={"message": "通知配置已删除"})


# ==================== 产品通知配置 ====================

@router.get("/products/{product_id}/config",
            response_model=ResponseBaseSchema[ProductNotificationConfigResponse],
            summary="获取产品通知配置")
async def get_product_notification_config(
    product_id: int = Path(..., ge=1, description="产品ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取产品的通知配置（已重构使用服务层）"""
    # 使用服务层（业务逻辑在NotificationConfigService中）
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    
    # 调用服务层获取产品通知配置（服务层会处理权限检查和验证）
    config = await notification_service.get_product_notification_config(product_id, current_user)
    
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
    """创建或更新产品的通知配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在NotificationConfigService中）
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    
    # 准备配置数据
    config_data = config_in.model_dump(exclude_unset=True)
    
    # 调用服务层创建或更新产品通知配置（服务层会处理验证和逻辑）
    config = await notification_service.create_or_update_product_notification_config(
        product_id, config_data, current_user
    )
    
    return ResponseBaseSchema.success(data=ProductNotificationConfigResponse.model_validate(config))


@router.delete("/products/{product_id}/config",
               response_model=ResponseBaseSchema[dict],
               summary="删除产品通知配置")
async def delete_product_notification_config(
    product_id: int = Path(..., ge=1, description="产品ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """删除产品的通知配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在NotificationConfigService中）
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    
    # 调用服务层删除产品通知配置（服务层会处理验证和删除）
    await notification_service.delete_product_notification_config(product_id, current_user)
    
    return ResponseBaseSchema.success(data={"message": "通知配置已删除"})


# ==================== 通知记录查询 ====================

@router.get("/notifications",
            response_model=PaginatedResponseBaseSchema[list[PostbackNotificationResponse]],
            summary="获取通知记录列表")
async def get_notification_records(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    conversion_id: Optional[int] = Query(None, description="转化记录ID过滤"),
    client_id: Optional[int] = Query(None, description="客户ID过滤"),
    product_id: Optional[int] = Query(None, description="产品ID过滤"),
    publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
    notification_status: Optional[str] = Query(None, description="通知状态过滤（sent, failed, pending）"),
    notification_channel: Optional[str] = Query(None, description="通知渠道过滤（telegram, email, sms, webhook）"),
    notification_type: Optional[str] = Query(None, description="通知类型过滤（conversion, high_value, error, forward, summary_hourly, summary_daily）"),
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取通知记录列表（支持分页和过滤，已重构使用服务层）"""
    # 使用服务层（业务逻辑在NotificationConfigService中）
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    
    # 调用服务层获取通知记录列表（服务层会处理查询、过滤、分页、自动创建等）
    notifications, total = await notification_service.get_notification_records(
        page=page,
        page_size=page_size,
        conversion_id=conversion_id,
        client_id=client_id,
        product_id=product_id,
        publisher_id=publisher_id,
        notification_status=notification_status,
        notification_channel=notification_channel,
        notification_type=notification_type,
        start_date=start_date,
        end_date=end_date,
        current_user=current_user
    )
    
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
    """获取通知记录详情（已重构使用服务层）"""
    # 使用服务层（业务逻辑在NotificationConfigService中）
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    
    # 调用服务层获取通知记录详情（服务层会处理权限检查）
    notification = await notification_service.get_notification_record_by_id(notification_id, current_user)
    
    return ResponseBaseSchema.success(data=PostbackNotificationResponse.model_validate(notification))


# ==================== 补发通知 ====================

@router.post("/conversions/{conversion_id}/resend-notification",
             response_model=ResponseBaseSchema[dict],
             summary="补发转化通知")
async def resend_conversion_notification(
    conversion_id: int = Path(..., ge=1, description="转化记录ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    补发转化通知（补发 Postback 转发给渠道）
    
    注意：补发通知是针对 Postback 的，应该补发 Postback 转发（发送给渠道 Publisher），
    不涉及 product_id 和 product.notification_address。
    
    如果转化记录没有转发记录或转发失败，可以手动补发转发。
    """
    # 使用服务层（业务逻辑在NotificationConfigService中）
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    
    # 调用服务层补发转化通知（服务层会处理权限检查和补发逻辑）
    result = await notification_service.resend_conversion_notification(conversion_id, current_user)
    
    return ResponseBaseSchema.success(data=result)


@router.post("/forward-logs/{forward_log_id}/resend-notification",
             response_model=ResponseBaseSchema[dict],
             summary="基于转发日志补发通知")
async def resend_notification_from_forward_log(
    forward_log_id: int = Path(..., ge=1, description="转发日志ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    基于转发日志补发通知（补发 Postback 转发给渠道）
    
    注意：补发通知是针对 Postback 的，应该补发 Postback 转发（发送给渠道 Publisher），
    不涉及 product_id 和 product.notification_address。
    
    根据转发日志中的转化记录，重新发送 Postback 转发给渠道。
    仅管理员可访问。
    """
    # 使用服务层（业务逻辑在NotificationConfigService中）
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    
    # 调用服务层基于转发日志补发通知（服务层会处理权限检查和补发逻辑）
    result = await notification_service.resend_notification_from_forward_log(forward_log_id, current_user)
    
    return ResponseBaseSchema.success(data=result)


@router.post("/conversions/batch-resend-notification",
             response_model=ResponseBaseSchema[dict],
             summary="批量补发转化通知")
async def batch_resend_conversion_notification(
    request_data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    批量补发转化通知（批量补发 Postback 转发给渠道）
    
    支持同时补发多条转化记录的通知，最多支持50条记录。
    
    请求体示例：
    {
      "conversion_ids": [1, 2, 3]
    }
    """
    conversion_ids = request_data.get("conversion_ids", [])
    
    if not isinstance(conversion_ids, list):
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail="conversion_ids 必须是数组格式"
        )
    
    # 使用服务层（业务逻辑在NotificationConfigService中）
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    
    # 调用服务层批量补发转化通知（服务层会处理权限检查和补发逻辑）
    result = await notification_service.batch_resend_conversion_notification(conversion_ids, current_user)
    
    return ResponseBaseSchema.success(data=result)


# ==================== 管理员通知配置 ====================

@router.get("/admin/config",
            response_model=ResponseBaseSchema[AdminNotificationConfigResponse],
            summary="获取管理员通知配置")
async def get_admin_notification_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    获取管理员通知配置
    
    仅管理员可访问
    如果配置不存在，返回默认配置
    """
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    config = await notification_service.get_admin_notification_config()
    
    if not config:
        # 返回默认配置
        return ResponseBaseSchema.success(data=AdminNotificationConfigResponse(
            id=0,
            telegram_enabled=True,
            telegram_chat_id=None,
            notify_all_conversions=True,
            notify_forward_failure=True,
            notify_forward_success=False,
            notify_system_errors=True,
            notify_statistics=False,
            statistics_frequency="hourly",
            created_at=None,
            updated_at=None
        ))
    
    return ResponseBaseSchema.success(data=AdminNotificationConfigResponse.model_validate(config))


@router.post("/admin/config",
             response_model=ResponseBaseSchema[AdminNotificationConfigResponse],
             summary="创建或更新管理员通知配置")
async def create_or_update_admin_notification_config(
    config_data: AdminNotificationConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    创建或更新管理员通知配置
    
    仅管理员可访问
    管理员通知配置是单例模式，只有一条记录（id=1）
    """
    notification_service: NotificationConfigService = await get_notification_config_service(db)
    config = await notification_service.create_or_update_admin_notification_config(
        config_data.model_dump(exclude_unset=True),
        current_user
    )
    
    return ResponseBaseSchema.success(data=AdminNotificationConfigResponse.model_validate(config))


@router.post("/admin/test-connection",
             response_model=ResponseBaseSchema[dict],
             summary="测试 Telegram 连接")
async def test_telegram_connection(
    request_data: TestConnectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    测试 Telegram 连接
    
    仅管理员可访问
    发送一条测试消息到指定的 Chat ID
    """
    
    telegram_chat_id = request_data.telegram_chat_id
    
    # 发送测试消息
    test_message = "🔔 Telegram 通知测试\n\n这是一条测试消息，如果您收到此消息，说明 Telegram 连接正常。"
    
    try:
        success = await send_telegram_message_async(telegram_chat_id, test_message)
        if success:
            return ResponseBaseSchema.success(data={
                "success": True,
                "message": "连接成功，测试消息已发送"
            })
        else:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="连接失败，请检查 Chat ID 是否正确"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"测试 Telegram 连接失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"测试连接失败: {str(e)}"
        )


@router.post("/admin/test-message",
             response_model=ResponseBaseSchema[dict],
             summary="发送测试消息")
async def send_test_message(
    request_data: TestMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    发送测试消息
    
    仅管理员可访问
    发送指定类型的测试消息到指定的 Chat ID
    """
    telegram_chat_id = request_data.telegram_chat_id
    message_type = request_data.message_type
    
    try:
        # 使用 TelegramNotificationService 构建测试消息
        test_message = TelegramNotificationService.build_test_message(message_type)
        
        success = await send_telegram_message_async(telegram_chat_id, test_message)
        if success:
            return ResponseBaseSchema.success(data={
                "success": True,
                "message": "测试消息已发送"
            })
        else:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="发送失败，请检查 Chat ID 是否正确"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发送测试消息失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"发送测试消息失败: {str(e)}"
        )

