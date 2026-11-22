"""
待确认 Postback 转化业务服务。

职责：
- 查询来自非白名单 IP 的 PendingPostbackConversion（分页、筛选）
- 管理员手动批准/拒绝；批准时写入 PostbackConversion 并回填归因
- IP 加白后批量自动批准（auto_approve_pending_by_ip），跳过已存在正式记录

确认入库须做幂等校验；长期积压可通过诊断服务排查归因失败原因。

对应路由：app/api_v1/postback（pending 子路由）
"""
import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.constants import MAX_PAGE_SIZE
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.pagination import calculate_pagination_offset
from app.core.postback.transformers.click_associator import ClickAssociator
from app.core.tracking.click_token import resolve_click_from_token
from app.core.utils import parse_date_to_app_timezone, get_app_now_naive
from app.core.postback.pending_lock import build_pending_for_update_statement
from app.core.postback.savers.conversion_saver import sanitize_postback_raw_data
from app.core.postback.approval_audit import (
    add_postback_approval_audit,
    persist_postback_approval_audit_independently,
)
from app.models.models import (
    PendingPostbackConversion, PostbackConversion, Product, Client, User
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.postback import PendingPostbackConversionResponse, PostbackConversionResponse

logger = logging.getLogger(__name__)


class PostbackPendingService:
    """
    待确认 Postback 转化服务。

    桥接「IP 未加白」与「正式转化入库」两个阶段；
    与 PostbackIpWhitelistService 联动实现运维加白即转正。
    """

    async def _resolve_click_assoc(
            self, pending: PendingPostbackConversion, db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        解析待确认记录的点击归因信息。

        优先从 click_token 内存解析，失败则查 clicks 表。

        Returns:
            含 offer_id、publisher_id、advertiser_id、click_time 的字典，或 None
        """
        if not pending.click_id:
            return None
        click_assoc = resolve_click_from_token(pending.click_id)
        if not click_assoc:
            click_assoc = await ClickAssociator.associate_from_db(
                pending.click_id, db
            )
        return click_assoc

    async def _pending_conversion_exists(
            self, pending: PendingPostbackConversion, db: AsyncSession
    ) -> Optional[int]:
        """
        查询同 platform + conversion_id + event_name 的正式转化记录 ID。

        返回主键而非布尔值，使重复审批审计也能准确关联既有转化记录。
        """
        existing = await db.execute(
            select(PostbackConversion.id).where(
                PostbackConversion.platform == pending.platform,
                PostbackConversion.conversion_id == pending.conversion_id,
                PostbackConversion.event_name == pending.event_name,
            )
        )
        return existing.scalars().first()

    async def _create_conversion_from_pending(
            self,
            pending: PendingPostbackConversion,
            db: AsyncSession,
    ) -> PostbackConversion:
        """
        由待确认记录构造 PostbackConversion 并标记 pending 为 approved。

        不执行 commit，由调用方统一提交事务。

        Returns:
            已 add 至 session 的 PostbackConversion（status=Pending）
        """
        click_assoc = await self._resolve_click_assoc(pending, db)
        conversion = PostbackConversion(
            platform=pending.platform,
            conversion_id=pending.conversion_id,
            click_id=pending.click_id,
            click_time=pending.click_time
            or (click_assoc.get("click_time") if click_assoc else None),
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
            offer_id=click_assoc.get("offer_id") if click_assoc else None,
            publisher_id=click_assoc.get("publisher_id") if click_assoc else None,
            advertiser_id=click_assoc.get("advertiser_id") if click_assoc else None,
            conversion_status="Pending",
            raw_data=(
                sanitize_postback_raw_data(pending.raw_data)
                if pending.raw_data is not None
                else None
            ),
            created_at=get_app_now_naive(),
        )
        db.add(conversion)
        pending.status = "approved"
        pending.approved_at = get_app_now_naive()
        return conversion

    async def auto_approve_pending_by_ip(
            self,
            ip_address: str,
            db: AsyncSession,
            current_user: User,
    ) -> Dict[str, Any]:
        """
        将指定来源 IP 下所有 pending 待确认记录批量批准。

        每条记录使用独立 SAVEPOINT：单条数据/约束错误回滚当前记录，
        不污染同批其它记录；整个批次仍由调用方统一提交外层事务。

        Returns:
            Dict: approved_count、skipped_count、failed_count、approved_ids
        """
        result = {
            "approved_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "approved_ids": [],
        }
        ip = (ip_address or "").strip()
        if not ip:
            return result

        pending_list = []
        try:
            pending_result = await db.execute(
                select(PendingPostbackConversion).where(
                    PendingPostbackConversion.request_ip == ip,
                    PendingPostbackConversion.status == "pending",
                ).with_for_update()
            )
            pending_list = pending_result.scalars().all()
            if not pending_list:
                return result

            logger.info(
                "找到 %s 条待确认记录，开始自动批准",
                len(pending_list),
            )

            for pending in pending_list:
                pending_id = pending.id
                row_outcome = None
                row_conversion_id = None
                previous_status = pending.status
                try:
                    # 每条记录单独建立保存点，避免一次 flush 失败使整个批次事务失效。
                    async with db.begin_nested():
                        existing_conversion_id = await self._pending_conversion_exists(pending, db)
                        if existing_conversion_id is not None:
                            pending.status = "approved"
                            pending.approved_at = get_app_now_naive()
                            row_outcome = "already_exists"
                            row_conversion_id = existing_conversion_id
                        else:
                            conversion = await self._create_conversion_from_pending(pending, db)
                            # 在保存点内先 flush 获取正式转化 ID，再写入同事务审批审计。
                            await db.flush()
                            row_outcome = "approved"
                            row_conversion_id = conversion.id

                        add_postback_approval_audit(
                            db,
                            pending_conversion_id=pending_id,
                            conversion_id=row_conversion_id,
                            actor_type="system_user",
                            actor_id=current_user.id,
                            source="ip_whitelist",
                            action="auto_approve",
                            outcome=row_outcome,
                            previous_status=previous_status,
                            new_status=pending.status,
                        )
                        # 确保约束错误在当前 SAVEPOINT 内暴露并回滚。
                        await db.flush()

                    # 只有 SAVEPOINT 成功释放后才更新成功计数。
                    if row_outcome == "already_exists":
                        result["skipped_count"] += 1
                    elif row_outcome == "approved":
                        result["approved_count"] += 1
                        result["approved_ids"].append(pending_id)
                except Exception as row_error:
                    # SAVEPOINT 回滚后若外层事务也已失效，不能继续处理后续记录。
                    if not db.is_active:
                        raise
                    result["failed_count"] += 1
                    logger.warning(
                        "自动批准待确认记录失败: pending_id=%s error_type=%s",
                        pending_id,
                        type(row_error).__name__,
                    )

            if result["approved_count"] > 0:
                logger.info(
                    "管理员 %s 添加 IP 白名单后自动批准 %s 条待确认转化",
                    current_user.username,
                    result["approved_count"],
                )
            # 不在此处 commit；由请求事务边界统一提交。
        except Exception as e:
            await db.rollback()
            logger.error(
                "批量自动批准事务失败，已回滚整个批次: error_type=%s",
                type(e).__name__,
            )
            # 外层事务回滚后，之前各 SAVEPOINT 的变更也全部撤销，成功计数必须清零。
            result = {
                "approved_count": 0,
                "skipped_count": 0,
                "failed_count": len(pending_list),
                "approved_ids": [],
            }

        return result

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
        分页查询待确认 Postback 转化（仅管理员）。

        记录来自非白名单 IP 的 Postback 请求，status 默认 pending。

        Args:
            platform: 平台标识过滤
            request_ip: 来源 IP 模糊匹配
            status: pending / approved / rejected
            start_date / end_date: 创建时间范围 YYYY-MM-DD
            page / page_size: 分页参数
            db: 异步数据库会话
            current_user: 当前管理员用户

        Returns:
            PaginatedResponseBaseSchema: 待确认列表及 total
        """
        offset = calculate_pagination_offset(
            page,
            page_size,
            resource_name="待确认 Postback 转化",
            max_page_size=1000,
        )
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
            query = query.order_by(PendingPostbackConversion.created_at.desc(), PendingPostbackConversion.id.desc())
            query = query.offset(offset).limit(page_size)

            result = await db.execute(query)
            pending_conversions = result.scalars().all()

            product_ids = list({p.product_id for p in pending_conversions if p.product_id})
            client_ids = list({p.client_id for p in pending_conversions if p.client_id})
            products_map = {}
            if product_ids:
                pr = await db.execute(
                    select(Product.id, Product.name).where(Product.id.in_(product_ids))
                )
                for row in pr.all():
                    products_map[row.id] = row.name
            clients_map = {}
            if client_ids:
                cr = await db.execute(
                    select(Client.id, Client.company_name).where(Client.id.in_(client_ids))
                )
                for row in cr.all():
                    clients_map[row.id] = row.company_name

            conversion_list = []
            for pending in pending_conversions:
                conversion_dict = PendingPostbackConversionResponse.model_validate(pending).model_dump(mode='json')
                if pending.product_id and pending.product_id in products_map:
                    conversion_dict["product_name"] = products_map[pending.product_id]
                if pending.client_id and pending.client_id in clients_map:
                    conversion_dict["client_name"] = clients_map[pending.client_id]
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
            logger.error(
                "查询待确认转化记录失败: error_type=%s",
                type(e).__name__,
            )
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="查询待确认转化记录失败，请稍后重试",
            )

    async def approve_pending_conversion(
            self,
            pending_id: int,
            db: AsyncSession,
            current_user: User
    ):
        """
        手动批准单条待确认记录（仅管理员）。

        写入 PostbackConversion 并将 pending.status 置为 approved。

        Args:
            pending_id: PendingPostbackConversion 主键
            db: 异步数据库会话
            current_user: 当前管理员用户

        Returns:
            ResponseBaseSchema: 新建 PostbackConversionResponse

        Raises:
            APIException: 记录不存在、已处理或正式记录已存在
        """
        audit_attempt = None
        try:
            # --- 加载 pending 并校验状态 ---
            result = await db.execute(
                build_pending_for_update_statement(PendingPostbackConversion, pending_id, status=None)
            )
            pending = result.scalars().first()

            if not pending:
                audit_attempt = {
                    "pending_conversion_id": pending_id,
                    "conversion_id": None,
                    "actor_type": "system_user",
                    "actor_id": current_user.id,
                    "source": "web",
                    "action": "approve",
                    "outcome": "not_found",
                    "previous_status": None,
                    "new_status": None,
                }
                raise_api_exception(
                    ErrorCode.NOT_FOUND,
                    detail=f"待确认记录 ID {pending_id} 不存在或已被处理"
                )

            if pending.status != "pending":
                audit_attempt = {
                    "pending_conversion_id": pending_id,
                    "conversion_id": None,
                    "actor_type": "system_user",
                    "actor_id": current_user.id,
                    "source": "web",
                    "action": "approve",
                    "outcome": "already_processed",
                    "previous_status": pending.status,
                    "new_status": pending.status,
                }
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"待确认记录已处理，当前状态：{pending.status}",
                )

            existing_conversion_id = await self._pending_conversion_exists(pending, db)
            if existing_conversion_id is not None:
                audit_attempt = {
                    "pending_conversion_id": pending_id,
                    "conversion_id": existing_conversion_id,
                    "actor_type": "system_user",
                    "actor_id": current_user.id,
                    "source": "web",
                    "action": "approve",
                    "outcome": "already_exists",
                    "previous_status": pending.status,
                    "new_status": pending.status,
                }
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail="该转化记录已存在，无法重复创建",
                )

            previous_status = pending.status
            conversion = await self._create_conversion_from_pending(pending, db)
            await db.flush()
            add_postback_approval_audit(
                db,
                pending_conversion_id=pending.id,
                conversion_id=conversion.id,
                actor_type="system_user",
                actor_id=current_user.id,
                source="web",
                action="approve",
                outcome="approved",
                previous_status=previous_status,
                new_status=pending.status,
            )
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
            if audit_attempt is not None:
                try:
                    await persist_postback_approval_audit_independently(
                        db.bind,
                        **audit_attempt,
                    )
                except Exception as audit_exc:
                    logger.warning(
                        "记录待确认批准拦截审计失败；error_type=%s",
                        type(audit_exc).__name__,
                    )
            raise
        except Exception as e:
            await db.rollback()
            logger.error(
                "批准待确认转化记录失败: error_type=%s",
                type(e).__name__,
            )
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="批准待确认转化记录失败，请稍后重试",
            )

    async def reject_pending_conversion(
            self,
            pending_id: int,
            db: AsyncSession,
            current_user: User
    ):
        """
        拒绝单条待确认记录（仅管理员）。

        仅更新 pending.status 为 rejected，不写入正式转化表。

        Args:
            pending_id: PendingPostbackConversion 主键
            db: 异步数据库会话
            current_user: 当前管理员用户

        Returns:
            ResponseBaseSchema: 含 id 与 status=rejected
        """
        audit_attempt = None
        try:
            # --- 加载 pending 并校验状态 ---
            result = await db.execute(
                build_pending_for_update_statement(PendingPostbackConversion, pending_id, status=None)
            )
            pending = result.scalars().first()

            if not pending:
                audit_attempt = {
                    "pending_conversion_id": pending_id,
                    "conversion_id": None,
                    "actor_type": "system_user",
                    "actor_id": current_user.id,
                    "source": "web",
                    "action": "reject",
                    "outcome": "not_found",
                    "previous_status": None,
                    "new_status": None,
                }
                raise_api_exception(
                    ErrorCode.NOT_FOUND,
                    detail=f"待确认记录 ID {pending_id} 不存在或已被处理"
                )

            if pending.status != "pending":
                audit_attempt = {
                    "pending_conversion_id": pending_id,
                    "conversion_id": None,
                    "actor_type": "system_user",
                    "actor_id": current_user.id,
                    "source": "web",
                    "action": "reject",
                    "outcome": "already_processed",
                    "previous_status": pending.status,
                    "new_status": pending.status,
                }
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"待确认记录已处理，当前状态：{pending.status}",
                )

            # 更新状态并在同一事务写入审计事件。
            previous_status = pending.status
            pending.status = 'rejected'
            pending.rejected_at = get_app_now_naive()

            add_postback_approval_audit(
                db,
                pending_conversion_id=pending.id,
                conversion_id=None,
                actor_type="system_user",
                actor_id=current_user.id,
                source="web",
                action="reject",
                outcome="rejected",
                previous_status=previous_status,
                new_status=pending.status,
            )
            await db.flush()

            logger.info(
                f"管理员 {current_user.username} 拒绝了待确认转化记录: "
                f"pending_id={pending_id}"
            )

            return ResponseBaseSchema.success(
                data={"id": pending_id, "status": "rejected"},
                message="已拒绝转化记录"
            )

        except HTTPException:
            if audit_attempt is not None:
                try:
                    await persist_postback_approval_audit_independently(
                        db.bind,
                        **audit_attempt,
                    )
                except Exception as audit_exc:
                    logger.warning(
                        "记录待确认拒绝拦截审计失败；error_type=%s",
                        type(audit_exc).__name__,
                    )
            raise
        except Exception as e:
            await db.rollback()
            logger.error(
                "拒绝待确认转化记录失败: error_type=%s",
                type(e).__name__,
            )
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="拒绝待确认转化记录失败，请稍后重试",
            )


postback_pending_service = PostbackPendingService()
PendingHandler = PostbackPendingService
pending_handler = postback_pending_service
