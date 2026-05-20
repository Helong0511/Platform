"""
Postback 下游转发日志查询与补发服务。
"""
import logging
from datetime import timedelta
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.postback import PostbackForwarder
from app.core.utils import parse_date_to_app_timezone
from app.models.models import PostbackForwardLog, PostbackConversion, User
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.postback import PostbackForwardLogResponse

logger = logging.getLogger(__name__)


class PostbackForwardLogService:
    async def list_forward_logs(
        self,
        *,
        conversion_id: Optional[int],
        product_id: Optional[int],
        publisher_id: Optional[int],
        success: Optional[bool],
        start_date: Optional[str],
        end_date: Optional[str],
        page: int,
        page_size: int,
        db: AsyncSession,
        current_user: User,
    ):
        try:
            conditions = []
            if conversion_id:
                conditions.append(PostbackForwardLog.conversion_id == conversion_id)
            if product_id:
                conditions.append(PostbackForwardLog.product_id == product_id)
            if publisher_id:
                conditions.append(PostbackForwardLog.publisher_id == publisher_id)
            if success is not None:
                conditions.append(PostbackForwardLog.success == success)

            if start_date:
                try:
                    start_dt = parse_date_to_app_timezone(start_date, is_end_date=False)
                    conditions.append(PostbackForwardLog.created_at >= start_dt)
                except ValueError:
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail="起始日期格式错误，应为 YYYY-MM-DD",
                    )

            if end_date:
                try:
                    end_dt = parse_date_to_app_timezone(end_date, is_end_date=True)
                    end_dt = end_dt + timedelta(days=1)
                    conditions.append(PostbackForwardLog.created_at < end_dt)
                except ValueError:
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail="结束日期格式错误，应为 YYYY-MM-DD",
                    )

            query = select(PostbackForwardLog)
            if conditions:
                query = query.where(and_(*conditions))
            query = query.order_by(PostbackForwardLog.created_at.desc())
            query = query.offset((page - 1) * page_size).limit(page_size)

            result = await db.execute(query)
            logs = result.scalars().all()

            count_query = select(func.count()).select_from(PostbackForwardLog)
            if conditions:
                count_query = count_query.where(and_(*conditions))
            total = (await db.execute(count_query)).scalar() or 0

            return PaginatedResponseBaseSchema.success(
                data=[PostbackForwardLogResponse.model_validate(log) for log in logs],
                total=total,
                page=page,
                page_size=page_size,
                message="查询成功",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"查询 PostBack 转发日志失败: {e}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"查询失败：{str(e)}",
            )

    async def resend_forward(
        self,
        *,
        forward_log_id: int,
        db: AsyncSession,
        current_user: User,
    ):
        try:
            result = await db.execute(
                select(PostbackForwardLog).where(PostbackForwardLog.id == forward_log_id)
            )
            forward_log = result.scalars().first()
            if not forward_log:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"转发日志 ID {forward_log_id} 不存在",
                )

            conv_result = await db.execute(
                select(PostbackConversion).where(
                    PostbackConversion.id == forward_log.conversion_id
                )
            )
            conversion = conv_result.scalars().first()
            if not conversion:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"转化记录 ID {forward_log.conversion_id} 不存在",
                )

            if forward_log.publisher_id:
                await PostbackForwarder.forward_to_publisher(conversion, db)
                message = f"已补发转发到渠道（Publisher ID: {forward_log.publisher_id}）"
            elif forward_log.product_id:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="产品下游转发功能已废弃，PostBack 数据只转发给渠道（Publisher）",
                )
            else:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="转发日志缺少 publisher_id，无法确定转发目标",
                )

            logger.info(
                f"用户 {current_user.id} 补发转发: forward_log_id={forward_log_id}, "
                f"conversion_id={forward_log.conversion_id}"
            )
            return ResponseBaseSchema.success(
                data={
                    "message": message,
                    "forward_log_id": forward_log_id,
                    "conversion_id": forward_log.conversion_id,
                }
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"补发 PostBack 转发失败: {e}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"补发失败：{str(e)}",
            )


    async def get_postback_forward_logs(
        self,
        request,
        conversion_id: Optional[int],
        product_id: Optional[int],
        publisher_id: Optional[int],
        success: Optional[bool],
        start_date: Optional[str],
        end_date: Optional[str],
        page: int,
        page_size: int,
        db: AsyncSession,
        current_user: User,
    ):
        return await self.list_forward_logs(
            conversion_id=conversion_id,
            product_id=product_id,
            publisher_id=publisher_id,
            success=success,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            db=db,
            current_user=current_user,
        )

    async def resend_postback_forward(
        self,
        forward_log_id: int,
        db: AsyncSession,
        current_user: User,
    ):
        return await self.resend_forward(
            forward_log_id=forward_log_id,
            db=db,
            current_user=current_user,
        )


postback_forward_log_service = PostbackForwardLogService()
