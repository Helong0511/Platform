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
from urllib.parse import urlsplit
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.pagination import calculate_pagination_offset
from app.core.exceptions import raise_api_exception
from app.core.postback.forwarder import (
    FORWARD_QUEUE_REBUILD_MARKER,
    _lock_conversion_for_queue_enqueue,
)
from app.core.utils import get_app_now_naive, parse_date_to_app_timezone
from app.models.models import (
    PostbackForwardLog,
    PostbackConversion,
    PostbackForwardQueue,
    User,
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.postback import PostbackForwardLogResponse

logger = logging.getLogger(__name__)


def _safe_forward_log_response(log: PostbackForwardLog) -> PostbackForwardLogResponse:
    """历史日志可能包含原始个人信息，API 只返回脱敏摘要。"""
    response = PostbackForwardLogResponse.model_validate(log)
    try:
        parsed_url = urlsplit(log.downstream_url or "")
        safe_url = (
            f"{parsed_url.scheme}://{parsed_url.netloc}"
            if parsed_url.scheme and parsed_url.netloc
            else "历史下游 URL 已脱敏"
        )
    except ValueError:
        safe_url = "历史下游 URL 已脱敏"

    return response.model_copy(
        update={
            "downstream_url": safe_url,
            "request_data": "历史请求载荷已脱敏" if log.request_data else None,
            "request_params": "历史请求参数已脱敏" if log.request_params else None,
            "response_body": None,
            "error_message": (
                "下游响应未满足成功检查规则"
                if log.error_message
                else None
            ),
        }
    )


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
        offset = calculate_pagination_offset(
            page,
            page_size,
            resource_name="Postback 转发日志",
            max_page_size=1000,
        )
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
            query = query.order_by(PostbackForwardLog.created_at.desc(), PostbackForwardLog.id.desc())
            query = query.offset(offset).limit(page_size)

            result = await db.execute(query)
            logs = result.scalars().all()

            count_query = select(func.count()).select_from(PostbackForwardLog)
            if conditions:
                count_query = count_query.where(and_(*conditions))
            total = (await db.execute(count_query)).scalar() or 0

            return PaginatedResponseBaseSchema.success(
                data=[_safe_forward_log_response(log) for log in logs],
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
        将人工补发请求写入统一转发队列，不在 API 请求内直接发送外部 HTTP。

        先锁定原转发日志并校验 PII 状态，再锁定 conversion 主记录，
        最后按 conversion + 精确目标检查活动队列任务。这样人工补发与自动
        失败入队共享同一串行化入口，且与 PII 清理通过日志行锁互斥。
        """
        try:
            result = await db.execute(
                select(PostbackForwardLog)
                .where(PostbackForwardLog.id == forward_log_id)
                .with_for_update()
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

            # 目标必须明确；Publisher/产品关联被删除后不可猜测或改投其它目标。
            publisher_id = forward_log.publisher_id
            product_id = forward_log.product_id
            if bool(publisher_id) == bool(product_id):
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="转发日志必须且只能包含一个有效的下游目标",
                )

            conversion_result = await db.execute(
                select(PostbackConversion).where(
                    PostbackConversion.id == forward_log.conversion_id
                )
            )
            conversion = conversion_result.scalars().first()
            if not conversion:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"转化记录 ID {forward_log.conversion_id} 不存在",
                )

            # 与自动失败入队使用同一 conversion 行锁，避免两个事务同时通过去重检查。
            if not await _lock_conversion_for_queue_enqueue(db, conversion.id):
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail="关联转化记录已不存在，无法补发",
                )

            target_filters = [
                PostbackForwardQueue.conversion_id == conversion.id,
                PostbackForwardQueue.publisher_id == publisher_id
                if publisher_id is not None
                else PostbackForwardQueue.publisher_id.is_(None),
                PostbackForwardQueue.product_id == product_id
                if product_id is not None
                else PostbackForwardQueue.product_id.is_(None),
            ]
            existing_result = await db.execute(
                select(PostbackForwardQueue)
                .where(*target_filters)
                .with_for_update()
            )
            if existing_result.scalars().first():
                raise_api_exception(
                    ErrorCode.CONFLICT,
                    detail="该下游目标已有待处理或正在执行的转发任务，请勿重复补发",
                )

            task = PostbackForwardQueue(
                conversion_id=conversion.id,
                publisher_id=publisher_id,
                product_id=product_id,
                # Worker 根据 conversion 和目标当前配置重建请求；
                # 历史日志中的 URL 可能是已展开的个人信息载荷，不能复制到重试队列。
                downstream_url=FORWARD_QUEUE_REBUILD_MARKER,
                request_method=forward_log.request_method or "GET",
                request_data=None,
                request_params=None,
                retry_count=0,
                next_retry_time=get_app_now_naive(),
            )
            db.add(task)
            await db.flush()

            logger.info(
                "人工补发已进入统一转发队列：user_id=%s forward_log_id=%s queue_id=%s target_type=%s",
                current_user.id,
                forward_log_id,
                task.id,
                "publisher" if publisher_id is not None else "product",
            )
            return ResponseBaseSchema.success(
                data={
                    "message": "已加入下游转发队列，将由后台 Worker 处理",
                    "forward_log_id": forward_log_id,
                    "conversion_id": conversion.id,
                    "queue_id": task.id,
                    "queued": True,
                }
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("补发 PostBack 转发失败：error_type=%s", type(e).__name__)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="补发失败，请查看受控服务端日志",
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
