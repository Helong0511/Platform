"""待确认转化记录处理模块"""
import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.constants import MAX_PAGE_SIZE
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.utils import parse_date_to_app_timezone, get_app_now_naive
from app.models.models import (
    PendingPostbackConversion, PostbackConversion, Product, Client, User
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.postback import PendingPostbackConversionResponse, PostbackConversionResponse

logger = logging.getLogger(__name__)


class PendingHandler:
    """待确认转化记录处理器"""

    async def get_pending_postback_conversions(
            self,
            platform: Optional[str],
            request_ip: Optional[str],
            status: Optional[str],
            start_date: Optional[str],
            end_date: Optional[str],
            page: int,
            page_size: int,
            db: AsyncSession,
            current_user: User
    ):
        """
        查询待确认 Postback 转化记录（仅管理员）
        这些记录来自不在白名单的 IP 地址
        """
        try:
            query = select(PendingPostbackConversion)
            conditions = []

            if platform:
                conditions.append(PendingPostbackConversion.platform == platform)

            if request_ip:
                conditions.append(PendingPostbackConversion.request_ip.like(f"%{request_ip}%"))

            if status:
                conditions.append(PendingPostbackConversion.status == status)

            # 日期范围过滤
            if start_date:
                try:
                    start_datetime = parse_date_to_app_timezone(start_date, is_end_date=False)
                    conditions.append(PendingPostbackConversion.created_at >= start_datetime)
                except ValueError:
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail="起始日期格式错误，请使用 YYYY-MM-DD 格式"
                    )

            if end_date:
                try:
                    end_datetime = parse_date_to_app_timezone(end_date, is_end_date=True)
                    conditions.append(PendingPostbackConversion.created_at <= end_datetime)
                except ValueError:
                    raise_api_exception(
                        ErrorCode.VALIDATION_ERROR,
                        detail="结束日期格式错误，请使用 YYYY-MM-DD 格式"
                    )

            if conditions:
                query = query.where(and_(*conditions))

            # 计算总数
            count_query = select(func.count(PendingPostbackConversion.id))
            if conditions:
                count_query = count_query.where(and_(*conditions))
            total_result = await db.execute(count_query)
            total = total_result.scalar() or 0

            # 分页查询
            query = query.order_by(PendingPostbackConversion.created_at.desc())
            query = query.offset((page - 1) * page_size).limit(page_size)

            result = await db.execute(query)
            pending_conversions = result.scalars().all()

            # 获取关联的产品和客户名称
            conversion_list = []
            for pending in pending_conversions:
                conversion_dict = PendingPostbackConversionResponse.model_validate(pending).model_dump()

                # 查询产品名称
                if pending.product_id:
                    product_result = await db.execute(
                        select(Product).where(Product.id == pending.product_id)
                    )
                    product = product_result.scalars().first()
                    if product:
                        conversion_dict["product_name"] = product.product_name

                # 查询客户名称
                if pending.client_id:
                    client_result = await db.execute(
                        select(Client).where(Client.id == pending.client_id)
                    )
                    client = client_result.scalars().first()
                    if client:
                        conversion_dict["client_name"] = client.client_name

                conversion_list.append(PendingPostbackConversionResponse(**conversion_dict))

            logger.info(
                f"管理员 {current_user.username} 查询待确认转化记录: "
                f"total={total}, page={page}, page_size={page_size}"
            )

            return PaginatedResponseBaseSchema.success(
                data=conversion_list,
                total=total,
                page=page,
                page_size=page_size,
                message=f"成功获取 {len(conversion_list)} 条记录，共 {total} 条"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"查询待确认转化记录失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"查询失败：{str(e)}"
            )

    async def approve_pending_conversion(
            self,
            pending_id: int,
            db: AsyncSession,
            current_user: User
    ):
        """
        批准待确认转化记录，创建正式转化记录（仅管理员）
        """
        try:
            # 查询待确认记录
            result = await db.execute(
                select(PendingPostbackConversion).where(
                    PendingPostbackConversion.id == pending_id,
                    PendingPostbackConversion.status == 'pending'
                )
            )
            pending = result.scalars().first()

            if not pending:
                raise_api_exception(
                    ErrorCode.NOT_FOUND,
                    detail=f"待确认记录 ID {pending_id} 不存在或已被处理"
                )

            # 检查是否已存在相同的转化记录
            existing = await db.execute(
                select(PostbackConversion).where(
                    PostbackConversion.platform == pending.platform,
                    PostbackConversion.conversion_id == pending.conversion_id,
                    PostbackConversion.event_name == pending.event_name
                )
            )
            if existing.scalars().first():
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail="该转化记录已存在，无法重复创建"
                )

            # 创建正式转化记录
            conversion = PostbackConversion(
                platform=pending.platform,
                conversion_id=pending.conversion_id,
                event_name=pending.event_name,
                event_value=pending.event_value,
                original_payout=pending.original_payout,
                payout=pending.payout,
                devad_id=pending.devad_id,
                os=pending.os,
                carrier=pending.carrier,
                ip=pending.ip,
                gid=pending.gid,
                product_id=pending.product_id,
                client_id=pending.client_id,
                conversion_status='Pending',
                raw_data=pending.raw_data,
                created_at=get_app_now_naive()
            )
            db.add(conversion)

            # 更新待确认记录状态
            pending.status = 'approved'
            pending.approved_at = get_app_now_naive()

            await db.commit()
            await db.refresh(conversion)

            # 构建响应
            conversion_response = PostbackConversionResponse.model_validate(conversion)

            logger.info(
                f"管理员 {current_user.username} 批准了待确认转化记录: "
                f"pending_id={pending_id}, conversion_id={conversion.id}"
            )

            return ResponseBaseSchema.success(
                data=conversion_response,
                message="已批准并创建转化记录"
            )

        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"批准待确认转化记录失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"批准失败：{str(e)}"
            )

    async def reject_pending_conversion(
            self,
            pending_id: int,
            db: AsyncSession,
            current_user: User
    ):
        """
        拒绝待确认转化记录（仅管理员）
        """
        try:
            # 查询待确认记录
            result = await db.execute(
                select(PendingPostbackConversion).where(
                    PendingPostbackConversion.id == pending_id,
                    PendingPostbackConversion.status == 'pending'
                )
            )
            pending = result.scalars().first()

            if not pending:
                raise_api_exception(
                    ErrorCode.NOT_FOUND,
                    detail=f"待确认记录 ID {pending_id} 不存在或已被处理"
                )

            # 更新状态
            pending.status = 'rejected'
            pending.rejected_at = get_app_now_naive()

            await db.commit()

            logger.info(
                f"管理员 {current_user.username} 拒绝了待确认转化记录: "
                f"pending_id={pending_id}"
            )

            return ResponseBaseSchema.success(
                data={"id": pending_id, "status": "rejected"},
                message="已拒绝转化记录"
            )

        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"拒绝待确认转化记录失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"拒绝失败：{str(e)}"
            )


pending_handler = PendingHandler()
