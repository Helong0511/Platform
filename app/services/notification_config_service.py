"""
通知配置管理服务层
封装客户和产品通知配置的业务逻辑
"""
import logging
from typing import Optional, List, Dict, Any, Tuple

from fastapi import HTTPException
from sqlalchemy import and_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.postback.forwarder import PostbackForwarder
from app.core.postback.notifier import PostbackNotifier
from app.core.utils import parse_date_to_app_timezone, get_app_now_naive
from app.models.models import (
    Client,
    Product,
    User,
    UserRole,
    ClientNotificationConfig,
    ProductNotificationConfig,
    AdminNotificationConfig,
    PostbackNotification,
    PostbackConversion,
    PostbackForwardLog
)

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
                        # 获取客户和产品信息（用于构建通知消息）
                        product = None
                        client = None

                        if conversion.product_id:
                            product_result = await self.db.execute(
                                select(Product).where(Product.id == conversion.product_id)
                            )
                            product = product_result.scalars().first()

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

                        # 使用统一的消息构建方法
                        client_name, user_full_name = await PostbackNotifier._get_client_info(client, self.db)
                        product_name = PostbackNotifier._get_product_name(product)

                        notification_message = PostbackNotifier._build_notification_message(
                            conversion=conversion,
                            client_name=client_name,
                            product_name=product_name,
                            user_full_name=user_full_name,
                            notification_type='conversion'
                        )

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
        补发转化通知（补发 Postback 转发给渠道）
        
        注意：补发通知是针对 Postback 的，应该补发 Postback 转发（发送给渠道 Publisher），
        不涉及 product_id 和 product.notification_address

        Args:
            conversion_id: 转化记录ID
            current_user: 当前用户

        Returns:
            Dict: 补发结果
        """

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
            # 补发 Postback 转发（发送给渠道 Publisher）
            # 不涉及 product_id，直接转发给渠道
            await PostbackForwarder.forward_to_publisher(
                conversion=conversion,
                db=self.db
            )

            logger.info(
                f"用户 {current_user.id} 补发转化通知: conversion_id={conversion_id}"
            )

            return {"message": "通知已补发", "conversion_id": conversion_id}
        except HTTPException:
            # HTTPException 是业务异常，直接重新抛出，不需要额外处理
            raise
        except Exception as e:
            # 提取错误信息
            error_msg = str(e)
            if hasattr(e, 'detail'):
                # 如果是 HTTPException，detail 可能是字典
                if isinstance(e.detail, dict):
                    error_msg = e.detail.get('detail', e.detail.get('message', str(e)))
                else:
                    error_msg = str(e.detail)

            logger.error(
                f"补发转化通知失败: conversion_id={conversion_id}, "
                f"error={error_msg}",
                exc_info=True
            )
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"补发通知失败: {error_msg}"
            )

    async def resend_notification_from_forward_log(
            self,
            forward_log_id: int,
            current_user: User
    ) -> Dict[str, Any]:
        """
        基于转发日志补发通知（补发 Postback 转发给渠道）
        
        注意：补发通知是针对 Postback 的，应该补发 Postback 转发（发送给渠道 Publisher），
        不涉及 product_id 和 product.notification_address

        Args:
            forward_log_id: 转发日志ID
            current_user: 当前用户

        Returns:
            Dict: 补发结果
        """

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

            # 补发 Postback 转发（发送给渠道 Publisher）
            # 不涉及 product_id，直接转发给渠道
            await PostbackForwarder.forward_to_publisher(
                conversion=conversion,
                db=self.db
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

    async def batch_resend_conversion_notification(
            self,
            conversion_ids: List[int],
            current_user: User
    ) -> Dict[str, Any]:
        """
        批量补发转化通知（批量补发 Postback 转发给渠道）
        
        Args:
            conversion_ids: 转化记录ID列表
            current_user: 当前用户

        Returns:
            Dict: 批量补发结果
        """
        if not conversion_ids:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="转化记录ID列表不能为空"
            )

        if len(conversion_ids) > 50:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="批量操作最多支持50条记录"
            )

        success_count = 0
        failed_count = 0
        failed_items = []

        for conversion_id in conversion_ids:
            try:
                # 查询转化记录
                result = await self.db.execute(
                    select(PostbackConversion).where(PostbackConversion.id == conversion_id)
                )
                conversion = result.scalars().first()

                if not conversion:
                    failed_items.append({
                        "conversion_id": conversion_id,
                        "error": f"转化记录ID {conversion_id} 不存在"
                    })
                    failed_count += 1
                    continue

                # 权限检查：管理员可以补发所有通知，客户只能补发自己客户的通知
                if current_user.role != UserRole.ADMIN:
                    if not current_user.client_id or conversion.client_id != current_user.client_id:
                        failed_items.append({
                            "conversion_id": conversion_id,
                            "error": "无权补发该转化记录的通知"
                        })
                        failed_count += 1
                        continue

                # 补发 Postback 转发（发送给渠道 Publisher）
                await PostbackForwarder.forward_to_publisher(
                    conversion=conversion,
                    db=self.db
                )

                logger.info(
                    f"用户 {current_user.id} 批量补发转化通知: conversion_id={conversion_id}"
                )

                success_count += 1
            except Exception as e:
                # 提取错误信息
                error_msg = str(e)
                if hasattr(e, 'detail'):
                    if isinstance(e.detail, dict):
                        error_msg = e.detail.get('detail', e.detail.get('message', str(e)))
                    else:
                        error_msg = str(e.detail)

                failed_items.append({
                    "conversion_id": conversion_id,
                    "error": error_msg
                })
                failed_count += 1
                logger.error(
                    f"批量补发转化通知失败: conversion_id={conversion_id}, error={error_msg}",
                    exc_info=True
                )

        return {
            "message": f"批量补发完成，成功 {success_count} 条，失败 {failed_count} 条",
            "success_count": success_count,
            "failed_count": failed_count,
            "failed_items": failed_items
        }

    # ==================== 管理员通知配置 ====================

    async def get_admin_notification_config(
            self
    ) -> Optional[AdminNotificationConfig]:
        """
        获取管理员通知配置
        
        Returns:
            Optional[AdminNotificationConfig]: 通知配置对象，如果不存在则返回None
        """
        # 管理员通知配置是单例模式，id 固定为 1
        result = await self.db.execute(
            select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
        )
        return result.scalars().first()

    async def create_or_update_admin_notification_config(
            self,
            config_data: Dict[str, Any],
            current_user: User
    ) -> AdminNotificationConfig:
        """
        创建或更新管理员通知配置
        
        Args:
            config_data: 配置数据
            current_user: 当前用户（必须是管理员）
        
        Returns:
            AdminNotificationConfig: 通知配置对象
        """
        # 检查是否已存在配置
        result = await self.db.execute(
            select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
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
                logger.info(f"管理员通知配置已更新")
                return existing_config
            except Exception as e:
                await self.db.rollback()
                logger.error(f"更新管理员通知配置失败: {str(e)}", exc_info=True)
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"更新管理员通知配置失败: {str(e)}"
                )
        else:
            # 创建新配置（id 固定为 1）
            new_config = AdminNotificationConfig(
                id=1,  # 固定为 1，单例模式
                **config_data
            )

            try:
                self.db.add(new_config)
                await self.db.commit()
                await self.db.refresh(new_config)
                logger.info(f"管理员通知配置已创建")
                return new_config
            except Exception as e:
                await self.db.rollback()
                logger.error(f"创建管理员通知配置失败: {str(e)}", exc_info=True)
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"创建管理员通知配置失败: {str(e)}"
                )
