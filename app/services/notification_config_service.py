"""
通知配置管理服务层
封装客户和产品通知配置的业务逻辑
"""
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func, delete

from app.models.models import (
    Client,
    Product,
    User,
    UserRole,
    ClientNotificationConfig,
    ProductNotificationConfig,
    PostbackNotification,
    PostbackConversion,
    PostbackForwardLog
)
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.utils import parse_date_to_app_timezone, get_app_now_naive
import logging

logger = logging.getLogger(__name__)


class NotificationConfigService:
    """通知配置服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== 客户通知配置 ====================

    async def get_client_notification_config(
        self,
        client_id: int,
        current_user: User
    ) -> Optional[ClientNotificationConfig]:
        """
        获取客户的通知配置

        Args:
            client_id: 客户ID
            current_user: 当前用户

        Returns:
            Optional[ClientNotificationConfig]: 通知配置对象，如果不存在则返回None
        """
        # 权限检查：管理员或客户本人
        if current_user.role != UserRole.ADMIN:
            if not current_user.client_id or current_user.client_id != client_id:
                raise_api_exception(
                    ErrorCode.ACCESS_DENIED,
                    detail="无权访问该客户的通知配置"
                )

        # 验证客户是否存在
        result = await self.db.execute(select(Client).where(Client.id == client_id))
        client = result.scalars().first()
        if not client:
            raise_api_exception(
                ErrorCode.CLIENT_NOT_FOUND,
                detail=f"客户ID {client_id} 不存在"
            )

        # 获取配置
        result = await self.db.execute(
            select(ClientNotificationConfig).where(ClientNotificationConfig.client_id == client_id)
        )
        return result.scalars().first()

    async def create_or_update_client_notification_config(
        self,
        client_id: int,
        config_data: Dict[str, Any],
        current_user: User
    ) -> ClientNotificationConfig:
        """
        创建或更新客户的通知配置

        Args:
            client_id: 客户ID
            config_data: 配置数据
            current_user: 当前用户

        Returns:
            ClientNotificationConfig: 通知配置对象
        """
        # 验证客户是否存在
        result = await self.db.execute(select(Client).where(Client.id == client_id))
        client = result.scalars().first()
        if not client:
            raise_api_exception(
                ErrorCode.CLIENT_NOT_FOUND,
                detail=f"客户ID {client_id} 不存在"
            )

        # 检查是否已存在配置
        result = await self.db.execute(
            select(ClientNotificationConfig).where(ClientNotificationConfig.client_id == client_id)
        )
        existing_config = result.scalars().first()

        if existing_config:
            # 更新现有配置
            for key, value in config_data.items():
                if hasattr(existing_config, key):
                    setattr(existing_config, key, value)

            try:
                await self.db.commit()
                await self.db.refresh(existing_config)
                logger.info(f"客户 {client_id} 的通知配置已更新")
                return existing_config
            except Exception as e:
                await self.db.rollback()
                logger.error(f"更新客户通知配置失败: {str(e)}", exc_info=True)
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"更新客户通知配置失败: {str(e)}"
                )
        else:
            # 创建新配置
            new_config = ClientNotificationConfig(
                client_id=client_id,
                **config_data
            )

            try:
                self.db.add(new_config)
                await self.db.commit()
                await self.db.refresh(new_config)
                logger.info(f"客户 {client_id} 的通知配置已创建")
                return new_config
            except Exception as e:
                await self.db.rollback()
                logger.error(f"创建客户通知配置失败: {str(e)}", exc_info=True)
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"创建客户通知配置失败: {str(e)}"
                )

    async def delete_client_notification_config(
        self,
        client_id: int,
        current_user: User
    ) -> None:
        """
        删除客户的通知配置

        Args:
            client_id: 客户ID
            current_user: 当前用户
        """
        result = await self.db.execute(
            select(ClientNotificationConfig).where(ClientNotificationConfig.client_id == client_id)
        )
        config = result.scalars().first()

        if not config:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"客户ID {client_id} 的通知配置不存在"
            )

        try:
            await self.db.execute(delete(ClientNotificationConfig).where(ClientNotificationConfig.id == config.id))
            await self.db.commit()
            logger.info(f"客户 {client_id} 的通知配置已删除")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"删除客户通知配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"删除客户通知配置失败: {str(e)}"
            )

    # ==================== 产品通知配置 ====================

    async def get_product_notification_config(
        self,
        product_id: int,
        current_user: User
    ) -> Optional[ProductNotificationConfig]:
        """
        获取产品的通知配置

        Args:
            product_id: 产品ID
            current_user: 当前用户

        Returns:
            Optional[ProductNotificationConfig]: 通知配置对象，如果不存在则返回None
        """
        # 验证产品是否存在
        result = await self.db.execute(select(Product).where(Product.id == product_id))
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
        result = await self.db.execute(
            select(ProductNotificationConfig).where(ProductNotificationConfig.product_id == product_id)
        )
        return result.scalars().first()

    async def create_or_update_product_notification_config(
        self,
        product_id: int,
        config_data: Dict[str, Any],
        current_user: User
    ) -> ProductNotificationConfig:
        """
        创建或更新产品的通知配置

        Args:
            product_id: 产品ID
            config_data: 配置数据
            current_user: 当前用户

        Returns:
            ProductNotificationConfig: 通知配置对象
        """
        # 验证产品是否存在
        result = await self.db.execute(select(Product).where(Product.id == product_id))
        product = result.scalars().first()
        if not product:
            raise_api_exception(
                ErrorCode.PRODUCT_NOT_FOUND,
                detail=f"产品ID {product_id} 不存在"
            )

        # 检查是否已存在配置
        result = await self.db.execute(
            select(ProductNotificationConfig).where(ProductNotificationConfig.product_id == product_id)
        )
        existing_config = result.scalars().first()

        if existing_config:
            # 更新现有配置
            for key, value in config_data.items():
                if hasattr(existing_config, key):
                    setattr(existing_config, key, value)

            try:
                await self.db.commit()
                await self.db.refresh(existing_config)
                logger.info(f"产品 {product_id} 的通知配置已更新")
                return existing_config
            except Exception as e:
                await self.db.rollback()
                logger.error(f"更新产品通知配置失败: {str(e)}", exc_info=True)
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"更新产品通知配置失败: {str(e)}"
                )
        else:
            # 创建新配置
            new_config = ProductNotificationConfig(
                product_id=product_id,
                **config_data
            )

            try:
                self.db.add(new_config)
                await self.db.commit()
                await self.db.refresh(new_config)
                logger.info(f"产品 {product_id} 的通知配置已创建")
                return new_config
            except Exception as e:
                await self.db.rollback()
                logger.error(f"创建产品通知配置失败: {str(e)}", exc_info=True)
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"创建产品通知配置失败: {str(e)}"
                )

    async def delete_product_notification_config(
        self,
        product_id: int,
        current_user: User
    ) -> None:
        """
        删除产品的通知配置

        Args:
            product_id: 产品ID
            current_user: 当前用户
        """
        result = await self.db.execute(
            select(ProductNotificationConfig).where(ProductNotificationConfig.product_id == product_id)
        )
        config = result.scalars().first()

        if not config:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"产品ID {product_id} 的通知配置不存在"
            )

        try:
            await self.db.execute(delete(ProductNotificationConfig).where(ProductNotificationConfig.id == config.id))
            await self.db.commit()
            logger.info(f"产品 {product_id} 的通知配置已删除")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"删除产品通知配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"删除产品通知配置失败: {str(e)}"
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
        current_user: User = None
    ) -> Tuple[List[PostbackNotification], int]:
        """
        获取通知记录列表

        Args:
            page: 页码
            page_size: 每页数量
            conversion_id: 转化记录ID过滤
            client_id: 客户ID过滤
            product_id: 产品ID过滤
            publisher_id: 渠道ID过滤
            notification_status: 通知状态过滤
            notification_channel: 通知渠道过滤
            notification_type: 通知类型过滤
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            current_user: 当前用户

        Returns:
            Tuple[List[PostbackNotification], int]: (通知记录列表, 总数)
        """
        # 权限检查：管理员可以查看所有，客户只能查看自己的
        query = select(PostbackNotification)

        if current_user.role != UserRole.ADMIN:
            # 客户只能查看自己客户的通知记录
            if not current_user.client_id:
                return [], 0
            query = query.where(PostbackNotification.client_id == current_user.client_id)

        # 应用过滤条件
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
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # 执行查询
        result = await self.db.execute(query)
        notifications = result.scalars().all()

        # 如果指定了 conversion_id 且没有找到通知记录，检查是否真的没有任何通知记录
        if conversion_id and total == 0:
            # 检查该转化记录是否真的没有任何通知记录（不考虑其他过滤条件）
            check_query = select(func.count(PostbackNotification.id)).where(
                PostbackNotification.conversion_id == conversion_id
            )
            # 如果是客户用户，添加客户ID限制
            if current_user.role != UserRole.ADMIN and current_user.client_id:
                check_query = check_query.where(PostbackNotification.client_id == current_user.client_id)

            check_result = await self.db.execute(check_query)
            existing_count = check_result.scalar() or 0

            # 如果确实没有任何通知记录，自动创建一个
            if existing_count == 0:
                try:
                    # 查询转化记录
                    conversion_result = await self.db.execute(
                        select(PostbackConversion).where(PostbackConversion.id == conversion_id)
                    )
                    conversion = conversion_result.scalars().first()

                    if conversion:
                        # 构建通知消息
                        notification_message = f"转化记录通知\n\n"
                        notification_message += f"转化ID: {conversion.conversion_id}\n"
                        notification_message += f"平台: {conversion.platform}\n"
                        if conversion.event_name:
                            notification_message += f"事件: {conversion.event_name}\n"

                        # 优先显示扣后的 payout（给下游的实际金额）
                        if conversion.payout is not None:
                            notification_message += f"金额 (PO): ${conversion.payout:.2f}\n"
                        elif conversion.original_payout is not None:
                            notification_message += f"金额 (PO): ${conversion.original_payout:.2f}\n"

                        # 原始金额作为参考（如果与扣后金额不同）
                        if conversion.original_payout is not None and conversion.payout is not None:
                            if conversion.original_payout != conversion.payout:
                                notification_message += f"原始金额 (PO): ${conversion.original_payout:.2f}\n"

                        if conversion.created_at:
                            time_str = conversion.created_at.strftime("%Y-%m-%d %H:%M:%S")
                            notification_message += f"时间: {time_str}\n"

                        # 创建通知记录
                        new_notification = PostbackNotification(
                            conversion_id=conversion.id,
                            client_id=conversion.client_id,
                            product_id=conversion.product_id,
                            publisher_id=None,
                            notification_type='conversion',
                            notification_channel='telegram',
                            notification_status='pending',
                            notification_message=notification_message,
                            auto_notify=False,
                            postback_url=None,
                            created_at=get_app_now_naive()
                        )

                        self.db.add(new_notification)
                        await self.db.commit()
                        await self.db.refresh(new_notification)

                        # 将新创建的通知记录添加到结果中
                        notifications = [new_notification]
                        total = 1

                        logger.info(
                            f"自动创建通知记录: conversion_id={conversion_id}, "
                            f"notification_id={new_notification.id}"
                        )
                except Exception as e:
                    logger.error(
                        f"自动创建通知记录失败: conversion_id={conversion_id}, error={str(e)}",
                        exc_info=True
                    )
                    await self.db.rollback()

        return notifications, total

    async def get_notification_record_by_id(
        self,
        notification_id: int,
        current_user: User
    ) -> PostbackNotification:
        """
        获取通知记录详情

        Args:
            notification_id: 通知记录ID
            current_user: 当前用户

        Returns:
            PostbackNotification: 通知记录对象
        """
        result = await self.db.execute(
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

        return notification

    # ==================== 补发通知 ====================

    async def resend_conversion_notification(
        self,
        conversion_id: int,
        current_user: User
    ) -> Dict[str, Any]:
        """
        补发转化通知

        Args:
            conversion_id: 转化记录ID
            current_user: 当前用户

        Returns:
            Dict: 补发结果
        """
        from app.core.postback.notifier import PostbackNotifier

        # 查询转化记录
        result = await self.db.execute(
            select(PostbackConversion).where(PostbackConversion.id == conversion_id)
        )
        conversion = result.scalars().first()

        if not conversion:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"转化记录ID {conversion_id} 不存在"
            )

        # 权限检查：管理员可以补发所有通知，客户只能补发自己客户的通知
        if current_user.role != UserRole.ADMIN:
            if not current_user.client_id or conversion.client_id != current_user.client_id:
                raise_api_exception(
                    ErrorCode.ACCESS_DENIED,
                    detail="无权补发该转化记录的通知"
                )

        try:
            # 补发通知（同步等待发送完成，而不是异步发送）
            # 获取客户和产品信息
            product = None
            client = None
            
            # 获取产品信息
            if conversion.product_id:
                product_result = await self.db.execute(
                    select(Product).where(Product.id == conversion.product_id)
                )
                product = product_result.scalars().first()
                
                # 如果 product_id 存在但查询不到产品，说明产品可能已被删除
                if not product:
                    logger.error(
                        f"补发通知失败: conversion_id={conversion_id}, "
                        f"product_id={conversion.product_id}, "
                        f"reason=产品不存在（可能已被删除）"
                    )
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail=f"转化记录关联的产品ID {conversion.product_id} 不存在，无法补发通知"
                    )
            
            # 获取客户信息
            if product and product.client_id:
                client_result = await self.db.execute(
                    select(Client).where(Client.id == product.client_id)
                )
                client = client_result.scalars().first()
            elif conversion.client_id:
                client_result = await self.db.execute(
                    select(Client).where(Client.id == conversion.client_id)
                )
                client = client_result.scalars().first()
            
            # 检查产品是否存在
            if not product:
                logger.error(
                    f"补发通知失败: conversion_id={conversion_id}, "
                    f"product_id=None, client_id={conversion.client_id}, "
                    f"reason=转化记录未关联产品"
                )
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="转化记录未关联产品，无法补发通知。请先为转化记录关联产品并配置通知地址"
                )
            
            # 检查产品是否配置了通知地址
            if not product.notification_address:
                logger.error(
                    f"补发通知失败: conversion_id={conversion_id}, "
                    f"product_id={product.id}, product_name={product.name}, "
                    f"reason=产品未配置通知地址"
                )
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail=f"产品「{product.name}」未配置通知地址，无法补发通知。请在产品管理中配置通知地址"
                )
            
            notification_address = product.notification_address.strip()
            if not notification_address:
                logger.error(
                    f"补发通知失败: conversion_id={conversion_id}, "
                    f"product_id={conversion.product_id}, "
                    f"reason=产品通知地址为空"
                )
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="产品通知地址为空，无法补发通知"
                )
            
            # 获取客户和产品信息（用于通知）
            client_name, user_full_name = await PostbackNotifier._get_client_info(client, self.db)
            product_name = PostbackNotifier._get_product_name(product)
            
            # 构建通知消息
            message = PostbackNotifier._build_notification_message(
                conversion=conversion,
                client_name=client_name,
                product_name=product_name,
                user_full_name=user_full_name,
                notification_type='conversion'
            )
            
            # 同步发送通知（等待发送完成，失败时抛出异常）
            success = await PostbackNotifier._send_notification_async(
                message=message,
                conversion=conversion,
                client=client,
                product=product,
                notification_address=notification_address,
                db=self.db,
                raise_on_failure=True  # 补发通知时，失败应该抛出异常
            )
            
            if not success:
                logger.error(
                    f"补发通知失败: conversion_id={conversion_id}, "
                    f"product_id={product.id if product else None}, "
                    f"client_id={client.id if client else None}, "
                    f"address={notification_address[:50]}, "
                    f"reason=通知发送失败"
                )
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail="通知发送失败，请检查通知地址配置"
                )

            logger.info(
                f"用户 {current_user.id} 补发转化通知: conversion_id={conversion_id}"
            )

            return {"message": "通知已补发", "conversion_id": conversion_id}
        except Exception as e:
            logger.error(
                f"补发转化通知失败: conversion_id={conversion_id}, error={str(e)}",
                exc_info=True
            )
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"补发通知失败: {str(e)}"
            )

    async def resend_notification_from_forward_log(
        self,
        forward_log_id: int,
        current_user: User
    ) -> Dict[str, Any]:
        """
        基于转发日志补发通知

        Args:
            forward_log_id: 转发日志ID
            current_user: 当前用户

        Returns:
            Dict: 补发结果
        """
        from app.core.postback.notifier import PostbackNotifier

        # 检查管理员权限
        if current_user.role != UserRole.ADMIN:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="仅管理员可访问此接口"
            )

        try:
            # 查询转发日志
            result = await self.db.execute(
                select(PostbackForwardLog).where(PostbackForwardLog.id == forward_log_id)
            )
            forward_log = result.scalars().first()

            if not forward_log:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"转发日志ID {forward_log_id} 不存在"
                )

            # 查询转化记录
            conversion_result = await self.db.execute(
                select(PostbackConversion).where(PostbackConversion.id == forward_log.conversion_id)
            )
            conversion = conversion_result.scalars().first()

            if not conversion:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"转化记录ID {forward_log.conversion_id} 不存在"
                )

            # 补发通知
            await PostbackNotifier.notify_conversion(
                conversion=conversion,
                db=self.db,
                product=None,
                client=None
            )

            logger.info(
                f"用户 {current_user.id} 基于转发日志补发通知: forward_log_id={forward_log_id}, "
                f"conversion_id={forward_log.conversion_id}"
            )

            return {
                "message": "通知已补发",
                "forward_log_id": forward_log_id,
                "conversion_id": forward_log.conversion_id
            }
        except Exception as e:
            logger.error(
                f"基于转发日志补发通知失败: forward_log_id={forward_log_id}, error={str(e)}",
                exc_info=True
            )
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"补发通知失败: {str(e)}"
            )

