"""
Postback 通知记录分页查询（含 conversion_id 空结果自动补建）。
"""
import logging
from typing import List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.postback.notifier import PostbackNotifier
from app.core.utils import get_app_now_naive, parse_date_to_app_timezone
from app.models.models import (
    Client,
    PostbackConversion,
    PostbackNotification,
    Product,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)


class NotificationRecordsQuery:
    """通知记录列表与详情查询。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch(
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
        query = select(PostbackNotification)

        if current_user.role != UserRole.ADMIN:
            if not current_user.client_id:
                return [], 0
            query = query.where(PostbackNotification.client_id == current_user.client_id)

        conditions = self._build_conditions(
            conversion_id,
            client_id,
            product_id,
            publisher_id,
            notification_status,
            notification_channel,
            notification_type,
            start_date,
            end_date,
        )
        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(PostbackNotification.created_at.desc())
        total = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar() or 0

        offset = (page - 1) * page_size
        notifications = (
            await self.db.execute(query.offset(offset).limit(page_size))
        ).scalars().all()

        if conversion_id and total == 0:
            notifications, total = await self._maybe_auto_create_for_conversion(
                conversion_id, current_user, notifications, total
            )

        return notifications, total

    async def fetch_by_id(
        self,
        notification_id: int,
        current_user: User,
    ) -> PostbackNotification:
        from app.services.notification.helpers import assert_notification_record_access

        notification = (
            await self.db.execute(
                select(PostbackNotification).where(PostbackNotification.id == notification_id)
            )
        ).scalars().first()

        if not notification:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"通知记录ID {notification_id} 不存在",
            )

        assert_notification_record_access(current_user, notification)
        return notification

    def _build_conditions(
        self,
        conversion_id,
        client_id,
        product_id,
        publisher_id,
        notification_status,
        notification_channel,
        notification_type,
        start_date,
        end_date,
    ):
        conditions = []
        if conversion_id:
            conditions.append(PostbackNotification.conversion_id == conversion_id)
        if client_id:
            conditions.append(PostbackNotification.client_id == client_id)
        if product_id:
            conditions.append(PostbackNotification.product_id == product_id)
        if publisher_id:
            conditions.append(PostbackNotification.publisher_id == publisher_id)
        if notification_status:
            conditions.append(PostbackNotification.notification_status == notification_status)
        if notification_channel:
            conditions.append(PostbackNotification.notification_channel == notification_channel)
        if notification_type:
            conditions.append(PostbackNotification.notification_type == notification_type)

        if start_date:
            try:
                start_dt = parse_date_to_app_timezone(start_date, is_end_date=False)
                conditions.append(PostbackNotification.created_at >= start_dt)
            except ValueError:
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="开始日期格式错误，应为 YYYY-MM-DD",
                )

        if end_date:
            try:
                end_dt = parse_date_to_app_timezone(end_date, is_end_date=True)
                conditions.append(PostbackNotification.created_at <= end_dt)
            except ValueError:
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="结束日期格式错误，应为 YYYY-MM-DD",
                )
        return conditions

    async def _maybe_auto_create_for_conversion(
        self,
        conversion_id: int,
        current_user: User,
        notifications: List[PostbackNotification],
        total: int,
    ) -> Tuple[List[PostbackNotification], int]:
        check_query = select(func.count(PostbackNotification.id)).where(
            PostbackNotification.conversion_id == conversion_id
        )
        if current_user.role != UserRole.ADMIN and current_user.client_id:
            check_query = check_query.where(
                PostbackNotification.client_id == current_user.client_id
            )

        existing_count = (await self.db.execute(check_query)).scalar() or 0
        if existing_count > 0:
            return notifications, total

        try:
            conversion = (
                await self.db.execute(
                    select(PostbackConversion).where(PostbackConversion.id == conversion_id)
                )
            ).scalars().first()
            if not conversion:
                return notifications, total

            product = None
            client = None
            if conversion.product_id:
                product = (
                    await self.db.execute(
                        select(Product).where(Product.id == conversion.product_id)
                    )
                ).scalars().first()

            if product and product.client_id:
                client = (
                    await self.db.execute(
                        select(Client).where(Client.id == product.client_id)
                    )
                ).scalars().first()
            elif conversion.client_id:
                client = (
                    await self.db.execute(
                        select(Client).where(Client.id == conversion.client_id)
                    )
                ).scalars().first()

            client_name, user_full_name = await PostbackNotifier._get_client_info(client, self.db)
            product_name = PostbackNotifier._get_product_name(product)
            notification_message = PostbackNotifier._build_notification_message(
                conversion=conversion,
                client_name=client_name,
                product_name=product_name,
                user_full_name=user_full_name,
                notification_type="conversion",
            )

            new_notification = PostbackNotification(
                conversion_id=conversion.id,
                client_id=conversion.client_id,
                product_id=conversion.product_id,
                publisher_id=None,
                notification_type="conversion",
                notification_channel="telegram",
                notification_status="pending",
                notification_message=notification_message,
                auto_notify=False,
                postback_url=None,
                created_at=get_app_now_naive(),
            )
            self.db.add(new_notification)
            await self.db.commit()
            await self.db.refresh(new_notification)
            logger.info(
                "自动创建通知记录: conversion_id=%s, notification_id=%s",
                conversion_id,
                new_notification.id,
            )
            return [new_notification], 1
        except Exception as e:
            logger.error(
                "自动创建通知记录失败: conversion_id=%s, error=%s",
                conversion_id,
                str(e),
                exc_info=True,
            )
            await self.db.rollback()
            return notifications, total
