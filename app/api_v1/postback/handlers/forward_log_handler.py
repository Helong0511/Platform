"""转发日志处理模块"""
import logging
from datetime import timedelta
from typing import Optional

from fastapi import Request, HTTPException
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.constants import MAX_PAGE_SIZE
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.postback import PostbackForwarder
from app.core.utils import parse_date_to_app_timezone
from app.models.models import PostbackForwardLog, PostbackConversion, User
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.postback import PostbackForwardLogResponse

logger = logging.getLogger(__name__)


class ForwardLogHandler:
    """转发日志处理器"""

    async def get_postback_forward_logs(
            self,
            request: Request,
            conversion_id: Optional[int],
            product_id: Optional[int],
            publisher_id: Optional[int],
            success: Optional[bool],
            start_date: Optional[str],
            end_date: Optional[str],
            page: int,
            page_size: int,
            db: AsyncSession,
            current_user: User
    ):
        """
        查询 PostBack 下游转发日志
        
        仅管理员可访问
        """
        try:
            # 构建查询条件
            conditions = []

            if conversion_id:
                conditions.append(PostbackForwardLog.conversion_id == conversion_id)
            if product_id:
                conditions.append(PostbackForwardLog.product_id == product_id)
            if publisher_id:
                conditions.append(PostbackForwardLog.publisher_id == publisher_id)
            if success is not None:
                conditions.append(PostbackForwardLog.success == success)

            # 日期范围过滤（使用应用时区，与数据库时间一致）
            if start_date:
                try:
                    start_dt = parse_date_to_app_timezone(start_date, is_end_date=False)
                    conditions.append(PostbackForwardLog.created_at >= start_dt)
                except ValueError:
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail="起始日期格式错误，应为 YYYY-MM-DD"
                    )

            if end_date:
                try:
                    end_dt = parse_date_to_app_timezone(end_date, is_end_date=True)
                    # 结束日期已包含整天（23:59:59.999999）
                    end_dt = end_dt + timedelta(days=1)
                    conditions.append(PostbackForwardLog.created_at < end_dt)
                except ValueError:
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail="结束日期格式错误，应为 YYYY-MM-DD"
                    )

            # 构建查询
            query = select(PostbackForwardLog)
            if conditions:
                query = query.where(and_(*conditions))

            # 按创建时间倒序排列
            query = query.order_by(PostbackForwardLog.created_at.desc())

            # 分页
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)

            # 执行查询
            result = await db.execute(query)
            logs = result.scalars().all()

            # 获取总数
            count_query = select(func.count()).select_from(PostbackForwardLog)
            if conditions:
                count_query = count_query.where(and_(*conditions))
            count_result = await db.execute(count_query)
            total = count_result.scalar() or 0

            return PaginatedResponseBaseSchema.success(
                data=[PostbackForwardLogResponse.model_validate(log) for log in logs],
                total=total,
                page=page,
                page_size=page_size,
                message="查询成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"查询 PostBack 转发日志失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"查询失败：{str(e)}"
            )

    async def resend_postback_forward(
            self,
            forward_log_id: int,
            db: AsyncSession,
            current_user: User
    ):
        """
        补发 PostBack 转发
        
        根据转发日志重新发送转发请求，用于处理转发失败的情况
        仅管理员可访问
        """
        try:
            # 查询转发日志
            result = await db.execute(
                select(PostbackForwardLog).where(PostbackForwardLog.id == forward_log_id)
            )
            forward_log = result.scalars().first()

            if not forward_log:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"转发日志ID {forward_log_id} 不存在"
                )

            # 查询转化记录
            conversion_result = await db.execute(
                select(PostbackConversion).where(PostbackConversion.id == forward_log.conversion_id)
            )
            conversion = conversion_result.scalars().first()

            if not conversion:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"转化记录ID {forward_log.conversion_id} 不存在"
                )

            # 根据转发类型重新发送（只支持转发到渠道）
            if forward_log.publisher_id:
                # 转发到渠道
                await PostbackForwarder.forward_to_publisher(conversion, db)
                message = f"已补发转发到渠道（Publisher ID: {forward_log.publisher_id}）"
            elif forward_log.product_id:
                # 产品下游转发已废弃，不再支持
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="产品下游转发功能已废弃，PostBack 数据只转发给渠道（Publisher）"
                )
            else:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="转发日志缺少 publisher_id，无法确定转发目标"
                )

            logger.info(
                f"用户 {current_user.id} 补发转发: forward_log_id={forward_log_id}, "
                f"conversion_id={forward_log.conversion_id}"
            )

            return ResponseBaseSchema.success(
                data={
                    "message": message,
                    "forward_log_id": forward_log_id,
                    "conversion_id": forward_log.conversion_id
                }
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"补发转发失败: forward_log_id={forward_log_id}, error={str(e)}",
                exc_info=True
            )
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"补发转发失败: {str(e)}"
            )


forward_log_handler = ForwardLogHandler()
