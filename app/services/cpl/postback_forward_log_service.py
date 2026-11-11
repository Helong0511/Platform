"""
Postback 下游转发日志查询与补发服务。

功能说明：
- 分页查询 PostbackForwardLog，支持按转化、产品、渠道、成功状态及日期筛选
- 根据历史转发日志手动触发补发，将转化再次转发至下游渠道（Publisher）
- 为 API 层提供 list / resend 两套命名别名，底层逻辑共用

在系统中的位置：
- 被管理端转发日志 API 调用；补发委托 ``PostbackForwarder``

注意事项：
1. 补发须记录新日志行，保留原始失败记录审计
2. 重复补发前检查下游是否已成功接收，避免重复计费
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
    """Postback 下游转发日志的查询与手动补发业务层。"""

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
        """
        分页查询下游转发日志。

        Args:
            conversion_id: 关联转化主键，可选。
            product_id: 产品 ID 筛选，可选。
            publisher_id: 渠道（Publisher）ID 筛选，可选。
            success: 转发是否成功，None 表示不限。
            start_date: 起始日期 YYYY-MM-DD，按应用时区解析。
            end_date: 结束日期 YYYY-MM-DD，含当日全天。
            page / page_size: 分页参数。
            db: 异步数据库会话。
            current_user: 当前登录用户（用于审计上下文，查询本身不做额外权限分支）。

        Returns:
            PaginatedResponseBaseSchema，data 为 PostbackForwardLogResponse 列表。
        """
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

            # 日期范围：结束日采用「次日零点前」左闭右开，避免漏掉当天记录
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
            logger.error("查询 PostBack 转发日志失败：%s", type(e).__name__)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="查询失败，请查看受控服务端日志",
            )

    async def resend_forward(
        self,
        *,
        forward_log_id: int,
        db: AsyncSession,
        current_user: User,
    ):
        """
        根据转发日志 ID 手动补发 Postback 至下游渠道。

        从日志还原 conversion_id，加载转化记录后调用 PostbackForwarder。
        支持渠道（publisher_id）与产品级（product_id）下游补发。

        Args:
            forward_log_id: PostbackForwardLog 主键。
            db: 异步数据库会话。
            current_user: 操作人，写入 info 日志。

        Returns:
            ResponseBaseSchema，data 含 message、forward_log_id、conversion_id。
        """
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
            if forward_log.pii_scrubbed_at is not None:
                raise_api_exception(
                    ErrorCode.CONFLICT,
                    detail="该转发日志已按保留策略清除载荷，不允许补发",
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
                await PostbackForwarder.forward_to_product(conversion, db)
                message = f"已补发转发到产品下游（Product ID: {forward_log.product_id}）"
            else:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="转发日志缺少 publisher_id / product_id，无法确定转发目标",
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
        """
        API 路由别名：分页查询转发日志，委托 list_forward_logs。

        request 参数保留以兼容路由签名，当前未使用。
        """
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
        """API 路由别名：补发转发，委托 resend_forward。"""
        return await self.resend_forward(
            forward_log_id=forward_log_id,
            db=db,
            current_user=current_user,
        )


postback_forward_log_service = PostbackForwardLogService()
