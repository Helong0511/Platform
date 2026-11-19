"""
通知配置权限与通用持久化辅助。
"""
import logging
from typing import Any, Dict, Optional, Type, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.models.models import (
    Client,
    PostbackConversion,
    PostbackNotification,
    Product,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)

ConfigModel = TypeVar("ConfigModel")


async def get_user_client_ids(db: AsyncSession, user: User) -> list[int]:
    """解析客户用户关联的全部启用 Client ID，并按 ID 稳定排序。"""
    if user.role != UserRole.CLIENT:
        return []
    result = await db.execute(
        select(Client.id)
        .where(
            Client.user_id == user.id,
            Client.is_active.is_(True),
        )
        .order_by(Client.id.asc())
    )
    return [int(client_id) for client_id in result.scalars().all() if client_id is not None]


async def assert_client_config_access(
    db: AsyncSession,
    current_user: User,
    client_id: int,
) -> None:
    """管理员或客户本人可访问客户通知配置。"""
    if current_user.role == UserRole.ADMIN:
        return
    user_client_ids = await get_user_client_ids(db, current_user)
    if client_id not in user_client_ids:
        raise_api_exception(
            ErrorCode.ACCESS_DENIED,
            detail="无权访问该客户的通知配置",
        )


async def assert_product_config_access(
    db: AsyncSession,
    current_user: User,
    product: Product,
) -> None:
    """管理员或产品所属客户可访问产品通知配置。"""
    if current_user.role == UserRole.ADMIN:
        return
    user_client_ids = await get_user_client_ids(db, current_user)
    if product.client_id not in user_client_ids:
        raise_api_exception(
            ErrorCode.ACCESS_DENIED,
            detail="无权访问该产品的通知配置",
        )


async def assert_notification_record_access(
    db: AsyncSession,
    current_user: User,
    notification: PostbackNotification,
) -> None:
    """客户仅能访问本 client_id 的通知记录。"""
    if current_user.role == UserRole.ADMIN:
        return
    user_client_ids = await get_user_client_ids(db, current_user)
    if notification.client_id not in user_client_ids:
        raise_api_exception(
            ErrorCode.ACCESS_DENIED,
            detail="无权访问该通知记录",
        )


async def assert_conversion_resend_access(
    db: AsyncSession,
    current_user: User,
    conversion: PostbackConversion,
) -> None:
    """补发权限：管理员或转化所属客户。"""
    if current_user.role == UserRole.ADMIN:
        return
    user_client_ids = await get_user_client_ids(db, current_user)
    if conversion.client_id not in user_client_ids:
        raise_api_exception(
            ErrorCode.ACCESS_DENIED,
            detail="无权补发该转化记录的通知",
        )


async def upsert_config(
    db: AsyncSession,
    existing_config: Optional[ConfigModel],
    model_class: Type[ConfigModel],
    create_kwargs: Dict[str, Any],
    config_data: Dict[str, Any],
    *,
    updated_log: str,
    created_log: str,
    update_fail_msg: str,
    create_fail_msg: str,
) -> ConfigModel:
    """通用通知配置 upsert（更新或新建）。"""
    if existing_config:
        for key, value in config_data.items():
            if hasattr(existing_config, key):
                setattr(existing_config, key, value)
        try:
            await db.flush()
            await db.refresh(existing_config)
            logger.info(updated_log)
            return existing_config
        except Exception as e:
            await db.rollback()
            logger.error("%s: %s", update_fail_msg, str(e), exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"{update_fail_msg}: {str(e)}",
            )

    new_config = model_class(**create_kwargs, **config_data)
    try:
        db.add(new_config)
        await db.flush()
        await db.refresh(new_config)
        logger.info(created_log)
        return new_config
    except Exception as e:
        await db.rollback()
        logger.error("%s: %s", create_fail_msg, str(e), exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"{create_fail_msg}: {str(e)}",
        )


async def delete_config(
    db: AsyncSession,
    config,
    *,
    log_msg: str,
    fail_msg: str,
) -> None:
    """删除单条通知配置记录。"""
    try:
        await db.delete(config)
        await db.flush()
        logger.info(log_msg)
    except Exception as e:
        await db.rollback()
        logger.error("%s: %s", fail_msg, str(e), exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"{fail_msg}: {str(e)}",
        )
