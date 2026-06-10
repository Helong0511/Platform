"""
Postback 通知补发命令。
"""
import logging
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.postback.forwarder import PostbackForwarder
from app.models.models import PostbackConversion, PostbackForwardLog, User, UserRole
from app.services.notification.helpers import assert_conversion_resend_access

logger = logging.getLogger(__name__)


class ResendNotificationCommand:
    """转化 Postback 补发（单条 / 批量 / 基于转发日志）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def resend_conversion(
        self,
        conversion_id: int,
        current_user: User,
    ) -> Dict[str, Any]:
        conversion = (
            await self.db.execute(
                select(PostbackConversion).where(PostbackConversion.id == conversion_id)
            )
        ).scalars().first()

        if not conversion:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"转化记录ID {conversion_id} 不存在",
            )

        assert_conversion_resend_access(current_user, conversion)

        try:
            await PostbackForwarder.forward_to_publisher(conversion=conversion, db=self.db)
            logger.info("用户 %s 补发转化通知: conversion_id=%s", current_user.id, conversion_id)
            return {"message": "通知已补发", "conversion_id": conversion_id}
        except HTTPException:
            raise
        except Exception as e:
            error_msg = self._extract_error_message(e)
            logger.error(
                "补发转化通知失败: conversion_id=%s, error=%s",
                conversion_id,
                error_msg,
                exc_info=True,
            )
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"补发通知失败: {error_msg}",
            )

    async def resend_from_forward_log(
        self,
        forward_log_id: int,
        current_user: User,
    ) -> Dict[str, Any]:
        if current_user.role != UserRole.ADMIN:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="仅管理员可访问此接口",
            )

        try:
            forward_log = (
                await self.db.execute(
                    select(PostbackForwardLog).where(PostbackForwardLog.id == forward_log_id)
                )
            ).scalars().first()
            if not forward_log:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"转发日志ID {forward_log_id} 不存在",
                )

            conversion = (
                await self.db.execute(
                    select(PostbackConversion).where(
                        PostbackConversion.id == forward_log.conversion_id
                    )
                )
            ).scalars().first()
            if not conversion:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"转化记录ID {forward_log.conversion_id} 不存在",
                )

            await PostbackForwarder.forward_to_publisher(conversion=conversion, db=self.db)
            logger.info(
                "用户 %s 基于转发日志补发通知: forward_log_id=%s, conversion_id=%s",
                current_user.id,
                forward_log_id,
                forward_log.conversion_id,
            )
            return {
                "message": "通知已补发",
                "forward_log_id": forward_log_id,
                "conversion_id": forward_log.conversion_id,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "基于转发日志补发通知失败: forward_log_id=%s, error=%s",
                forward_log_id,
                str(e),
                exc_info=True,
            )
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"补发通知失败: {str(e)}",
            )

    async def batch_resend_conversions(
        self,
        conversion_ids: List[int],
        current_user: User,
    ) -> Dict[str, Any]:
        if not conversion_ids:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="转化记录ID列表不能为空",
            )
        if len(conversion_ids) > 50:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="批量操作最多支持50条记录",
            )

        success_count = 0
        failed_count = 0
        failed_items = []

        conversions_by_id = {
            c.id: c
            for c in (
                await self.db.execute(
                    select(PostbackConversion).where(
                        PostbackConversion.id.in_(conversion_ids)
                    )
                )
            ).scalars().all()
        }

        for conversion_id in conversion_ids:
            try:
                conversion = conversions_by_id.get(conversion_id)
                if not conversion:
                    failed_items.append({
                        "conversion_id": conversion_id,
                        "error": f"转化记录ID {conversion_id} 不存在",
                    })
                    failed_count += 1
                    continue

                if current_user.role != UserRole.ADMIN:
                    if (
                        not current_user.client_id
                        or conversion.client_id != current_user.client_id
                    ):
                        failed_items.append({
                            "conversion_id": conversion_id,
                            "error": "无权补发该转化记录的通知",
                        })
                        failed_count += 1
                        continue

                await PostbackForwarder.forward_to_publisher(
                    conversion=conversion, db=self.db
                )
                logger.info(
                    "用户 %s 批量补发转化通知: conversion_id=%s",
                    current_user.id,
                    conversion_id,
                )
                success_count += 1
            except Exception as e:
                failed_items.append({
                    "conversion_id": conversion_id,
                    "error": self._extract_error_message(e),
                })
                failed_count += 1
                logger.error(
                    "批量补发转化通知失败: conversion_id=%s, error=%s",
                    conversion_id,
                    self._extract_error_message(e),
                    exc_info=True,
                )

        return {
            "message": f"批量补发完成，成功 {success_count} 条，失败 {failed_count} 条",
            "success_count": success_count,
            "failed_count": failed_count,
            "failed_items": failed_items,
        }

    @staticmethod
    def _extract_error_message(exc: Exception) -> str:
        if hasattr(exc, "detail"):
            detail = exc.detail
            if isinstance(detail, dict):
                return detail.get("detail", detail.get("message", str(exc)))
            return str(detail)
        return str(exc)
