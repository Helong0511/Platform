"""
通知配置管理服务层（薄编排层）。

功能说明：
- 客户/产品/管理员通知配置 CRUD
- 通知记录查询与 Postback 补发
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.models.models import (
    AdminNotificationConfig,
    Client,
    ClientNotificationConfig,
    PostbackNotification,
    Product,
    ProductNotificationConfig,
    User,
)
from app.services.notification.commands.resend_command import ResendNotificationCommand
from app.services.notification.helpers import (
    assert_client_config_access,
    assert_product_config_access,
    delete_config,
    upsert_config,
)
from app.services.notification.queries.records_query import NotificationRecordsQuery

logger = logging.getLogger(__name__)


class NotificationConfigService:
    """通知配置与通知记录服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== 客户通知配置 ====================

    async def get_client_notification_config(
        self,
        client_id: int,
        current_user: User,
    ) -> Optional[ClientNotificationConfig]:
        await assert_client_config_access(self.db, current_user, client_id)

        client = (
            await self.db.execute(select(Client).where(Client.id == client_id))
        ).scalars().first()
        if not client:
            raise_api_exception(
                ErrorCode.CLIENT_NOT_FOUND,
                detail=f"客户ID {client_id} 不存在",
            )

        return (
            await self.db.execute(
                select(ClientNotificationConfig).where(
                    ClientNotificationConfig.client_id == client_id
                )
            )
        ).scalars().first()

    async def create_or_update_client_notification_config(
        self,
        client_id: int,
        config_data: Dict[str, Any],
        current_user: User,
    ) -> ClientNotificationConfig:
        client = (
            await self.db.execute(select(Client).where(Client.id == client_id))
        ).scalars().first()
        if not client:
            raise_api_exception(
                ErrorCode.CLIENT_NOT_FOUND,
                detail=f"客户ID {client_id} 不存在",
            )

        existing = (
            await self.db.execute(
                select(ClientNotificationConfig).where(
                    ClientNotificationConfig.client_id == client_id
                )
            )
        ).scalars().first()

        return await upsert_config(
            self.db,
            existing,
            ClientNotificationConfig,
            {"client_id": client_id},
            config_data,
            updated_log=f"客户 {client_id} 的通知配置已更新",
            created_log=f"客户 {client_id} 的通知配置已创建",
            update_fail_msg="更新客户通知配置失败",
            create_fail_msg="创建客户通知配置失败",
        )

    async def delete_client_notification_config(
        self,
        client_id: int,
        current_user: User,
    ) -> None:
        config = (
            await self.db.execute(
                select(ClientNotificationConfig).where(
                    ClientNotificationConfig.client_id == client_id
                )
            )
        ).scalars().first()
        if not config:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"客户ID {client_id} 的通知配置不存在",
            )
        await delete_config(
            self.db,
            config,
            log_msg=f"客户 {client_id} 的通知配置已删除",
            fail_msg="删除客户通知配置失败",
        )

    # ==================== 产品通知配置 ====================

    async def get_product_notification_config(
        self,
        product_id: int,
        current_user: User,
    ) -> Optional[ProductNotificationConfig]:
        product = (
            await self.db.execute(select(Product).where(Product.id == product_id))
        ).scalars().first()
        if not product:
            raise_api_exception(
                ErrorCode.PRODUCT_NOT_FOUND,
                detail=f"产品ID {product_id} 不存在",
            )

        await assert_product_config_access(self.db, current_user, product)

        return (
            await self.db.execute(
                select(ProductNotificationConfig).where(
                    ProductNotificationConfig.product_id == product_id
                )
            )
        ).scalars().first()

    async def create_or_update_product_notification_config(
        self,
        product_id: int,
        config_data: Dict[str, Any],
        current_user: User,
    ) -> ProductNotificationConfig:
        product = (
            await self.db.execute(select(Product).where(Product.id == product_id))
        ).scalars().first()
        if not product:
            raise_api_exception(
                ErrorCode.PRODUCT_NOT_FOUND,
                detail=f"产品ID {product_id} 不存在",
            )

        existing = (
            await self.db.execute(
                select(ProductNotificationConfig).where(
                    ProductNotificationConfig.product_id == product_id
                )
            )
        ).scalars().first()

        return await upsert_config(
            self.db,
            existing,
            ProductNotificationConfig,
            {"product_id": product_id},
            config_data,
            updated_log=f"产品 {product_id} 的通知配置已更新",
            created_log=f"产品 {product_id} 的通知配置已创建",
            update_fail_msg="更新产品通知配置失败",
            create_fail_msg="创建产品通知配置失败",
        )

    async def delete_product_notification_config(
        self,
        product_id: int,
        current_user: User,
    ) -> None:
        config = (
            await self.db.execute(
                select(ProductNotificationConfig).where(
                    ProductNotificationConfig.product_id == product_id
                )
            )
        ).scalars().first()
        if not config:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"产品ID {product_id} 的通知配置不存在",
            )
        await delete_config(
            self.db,
            config,
            log_msg=f"产品 {product_id} 的通知配置已删除",
            fail_msg="删除产品通知配置失败",
        )

    # ==================== 通知记录查询 ====================

    async def get_notification_records(
        self,
        page: int = 1,
        page_size: int = 20,
        conversion_id: Optional[int] = None,
        client_id: Optional[int] = None,
        product_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        notification_status: Optional[str] = None,
        notification_channel: Optional[str] = None,
        notification_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        current_user: User = None,
    ) -> Tuple[List[PostbackNotification], int]:
        return await NotificationRecordsQuery(self.db).fetch(
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
            current_user=current_user,
        )

    async def get_notification_record_by_id(
        self,
        notification_id: int,
        current_user: User,
    ) -> PostbackNotification:
        return await NotificationRecordsQuery(self.db).fetch_by_id(
            notification_id, current_user
        )

    # ==================== 补发通知 ====================

    async def resend_conversion_notification(
        self,
        conversion_id: int,
        current_user: User,
    ) -> Dict[str, Any]:
        return await ResendNotificationCommand(self.db).resend_conversion(
            conversion_id, current_user
        )

    async def resend_notification_from_forward_log(
        self,
        forward_log_id: int,
        current_user: User,
    ) -> Dict[str, Any]:
        return await ResendNotificationCommand(self.db).resend_from_forward_log(
            forward_log_id, current_user
        )

    async def batch_resend_conversion_notification(
        self,
        conversion_ids: List[int],
        current_user: User,
    ) -> Dict[str, Any]:
        return await ResendNotificationCommand(self.db).batch_resend_conversions(
            conversion_ids, current_user
        )

    # ==================== 管理员通知配置 ====================

    async def get_admin_notification_config(self) -> Optional[AdminNotificationConfig]:
        return (
            await self.db.execute(
                select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
            )
        ).scalars().first()

    async def create_or_update_admin_notification_config(
        self,
        config_data: Dict[str, Any],
        current_user: User,
    ) -> AdminNotificationConfig:
        existing = (
            await self.db.execute(
                select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
            )
        ).scalars().first()

        return await upsert_config(
            self.db,
            existing,
            AdminNotificationConfig,
            {"id": 1},
            config_data,
            updated_log="管理员通知配置已更新",
            created_log="管理员通知配置已创建",
            update_fail_msg="更新管理员通知配置失败",
            create_fail_msg="创建管理员通知配置失败",
        )
