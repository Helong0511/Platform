"""
Postback 统一处理器模块（重构版）

协调各子模块完成 Postback 处理流程：
1. IP 验证 → 2. 数据验证 → 3. 数据标准化 → 4. Click 关联 → 5. 重复检测
6. 扣量计算 → 7. Cap 原子预留 → 8. 保存记录 → 9. 渠道转发 → 10. 通知发送

说明：入库 commit 后，渠道/产品转发改为后台任务（独立 DB 会话），
避免下游慢/超时时阻塞上游 PostBack 回调响应。
"""
import asyncio
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postback.errors import DeductionProcessingError
from app.core.postback.pipeline import attribution_ids_from_association
from app.core.postback.validators.ip_validator import IpValidator
from app.core.postback.validators.data_validator import DataValidator
from app.core.postback.transformers.normalizer import DataNormalizer
from app.core.postback.checks.cap_checker import CapChecker
from app.core.postback.pipeline import (
    PostbackPipelineContext,
    step_apply_discount,
    step_associate_click,
    step_check_duplicate,
    step_save_conversion,
    step_validate_offer_status,
    deactivate_short_links_on_cap_exceeded,
    conversion_status_for_cap,
)
from app.core.postback.forwarder import PostbackForwarder
from app.core.postback.notifier import PostbackNotifier
from app.models.models import (
    AdminNotificationConfig,
    CloakConfig,
    PostbackConversion,
    PostbackForwardQueue,
    Publisher,
    Product,
    ShortLink,
)
from app.services.telegram_notification_service import TelegramNotificationService
from app.services.third_party_report_outbox import (
    enqueue_postback_report,
    process_postback_report_outbox,
)
from app.core.utils import get_app_now_naive
from app.services.cap_reservation_ledger import CapReservationLedger
from app.core.url.url_params_util import (
    parse_stored_url_params,
    resolve_dp_from_url_params,
    scalar_query_value,
)

logger = logging.getLogger(__name__)


class PostbackProcessor:
    """Postback 统一处理器"""
    
    @staticmethod
    async def _conversion_event_exists(
        *,
        db: AsyncSession,
        platform: str,
        conversion_id: str,
        event_name: str,
    ) -> bool:
        """IntegrityError 后仅在事件唯一键已存在时判定为并发重复。"""
        result = await db.execute(
            select(PostbackConversion.id)
            .where(
                PostbackConversion.platform == platform,
                PostbackConversion.conversion_id == conversion_id,
                PostbackConversion.event_name == event_name,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def process(
        platform: str,
        raw_data: Dict[str, Any],
        db: AsyncSession,
        request_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        处理 postback 回调
        
        Args:
            platform: 平台名称
            raw_data: 原始请求数据
            db: 数据库会话
            request_ip: 请求 IP 地址
            
        Returns:
            处理结果字典
        """
        # 详细日志：开始处理 Postback
        logger.info(f"=== PostBack 接收处理开始 ===")
        logger.info(f"平台: {platform}")
        logger.info("请求 IP 已接收：present=%s", bool(request_ip))
        logger.debug(f"原始数据键: {list(raw_data.keys()) if isinstance(raw_data, dict) else type(raw_data)}")

        # Redis Cap reservation 不参与数据库事务；任何未提交阶段的异常都必须精确回退。
        # 一旦进入 COMMIT reconciliation，则由该函数根据数据库实际提交结果负责处理，
        # 外层异常处理不得再次 DECR，避免重复回退造成 Cap 计数虚低。
        cap_reservations: list[tuple] = []
        cap_rollback_attempted = False
        cap_commit_reconciliation_started = False
        third_party_report_outbox_id: Optional[int] = None

        try:
            # ========== 第 1 步：IP 验证 ==========
            logger.info("=== 第 1 步：IP 验证 ===")
            ip_valid, cleaned_ip = await IpValidator.validate(request_ip, db)
            logger.info("IP 验证结果: valid=%s", ip_valid)
            
            if not ip_valid:
                logger.warning("IP 验证失败，处理失败流程")
                return await PostbackProcessor._handle_ip_failure(platform, raw_data, db)
            
            # ========== 第 2 步：数据验证 ==========
            logger.info("=== 第 2 步：数据验证 ===")
            # 优先使用平台特定处理器
            from app.core.postback.handlers import get_handler
            handler = get_handler(platform)
            
            if handler:
                logger.info(f"使用平台特定处理器: {handler.__class__.__name__}")
                # 使用平台特定处理器验证
                data_valid, error_msg = await handler.validate(raw_data)
                if not data_valid:
                    logger.warning("数据验证失败：platform=%s", platform)
                    return {
                        "success": True,
                        "message": "数据验证失败",
                        "errors": [error_msg] if error_msg else []
                    }
                
                # ========== 第 3 步：数据标准化 ==========
                logger.info("=== 第 3 步：数据标准化 ===")
                normalized_data = await handler.normalize(raw_data)
            else:
                logger.info("使用通用验证和标准化")
                # 回退到通用验证和标准化
                data_valid, errors = DataValidator.validate(raw_data, platform)
                if not data_valid:
                    logger.warning("数据验证失败：platform=%s error_count=%s", platform, len(errors))
                    return {
                        "success": True,
                        "message": "数据验证失败",
                        "errors": errors
                    }
                
                # ========== 第 3 步：数据标准化 ==========
                logger.info("=== 第 3 步：数据标准化 ===")
                normalized_data = DataNormalizer.normalize(raw_data, platform)
            
            logger.info("Postback 数据标准化完成：field_count=%s", len(normalized_data))
            
            # ========== 第 4 步：Click ID 关联 ==========
            logger.info("=== 第 4 步：Click ID 关联 ===")
            click_id = normalized_data.get('click_id')
            logger.info("Click ID 关联开始：click_id_present=%s", bool(click_id))
            
            pipe_ctx = PostbackPipelineContext(
                platform=platform,
                raw_data=raw_data,
                db=db,
                request_ip=request_ip,
                normalized_data=normalized_data,
            )
            click_association = await step_associate_click(pipe_ctx)
            click_association = pipe_ctx.click_association

            logger.info(
                "Click 关联完成：field_count=%s",
                len(click_association) if isinstance(click_association, dict) else 0,
            )

            # ========== 第 4.5 步：Offer 激活状态校验 ==========
            logger.info("=== 第 4.5 步：Offer 激活状态校验 ===")
            offer_active = await step_validate_offer_status(pipe_ctx)
            if not offer_active:
                logger.warning("Offer 已下线，跳过转化处理：platform=%s", platform)
                return {
                    "success": True,
                    "message": "Offer 已下线，转化未处理",
                    "retryable": False,
                }

            # ========== 第 5 步：重复检测 ==========
            logger.info("=== 第 5 步：重复检测 ===")
            conversion_id = normalized_data.get('conversion_id')
            event_name = normalized_data.get('event_name')
            logger.info("检测重复：platform=%s event_name=%s", platform, event_name)

            pipe_ctx.normalized_data = normalized_data
            is_dup = await step_check_duplicate(pipe_ctx)

            if is_dup:
                logger.info(f"检测到重复转化，跳过处理：platform={platform}")
                return {
                    "success": True,
                    "message": "重复转化，已跳过",
                    "retryable": False,
                }

            # ========== 第 6–8 步：扣量 / Cap 原子预留 / 保存 ==========
            # Cap 不再先 peek 再 increment（TOCTOU）；扣量命中不占 Cap 名额，
            # 故仍先扣量，再对需入库转化做 Redis Lua 原子预留。
            logger.info("=== 第 6/7 步：扣量计算（Cap 预留延后至入库前） ===")
            pipe_ctx.click_association = click_association
            try:
                final_payout, deduction_info, skip_save_and_forward = await step_apply_discount(pipe_ctx)
            except DeductionProcessingError as ded_err:
                await db.rollback()
                logger.error("扣量计算失败，已回滚：error_type=%s", type(ded_err).__name__)
                return {
                    "success": False,
                    "message": "扣量计算失败，请重试",
                    "retryable": True,
                }
            logger.info(
                f"扣量计算结果：final_payout={final_payout}, skip_save={skip_save_and_forward}"
            )

            if skip_save_and_forward:
                await db.commit()
                logger.info("扣量命中，已记录日志，跳过入库与下游转发")
                return {
                    "success": True,
                    "message": "转化已扣量，未入库",
                    "platform": platform,
                    "payout": float(Decimal("0")),
                }

            offer_id, publisher_id, advertiser_id = attribution_ids_from_association(
                click_association
            )

            # Cap 原子预留（替代原先 check + increment 分离）
            cap_ok = True
            cap_status = "cap_ok"
            logger.info("=== Cap 原子预留 ===")
            try:
                cap_incremented, cap_status, cap_reservations = (
                    await CapChecker.increment_with_reservations(
                        offer_id=offer_id,
                        publisher_id=publisher_id,
                        advertiser_id=advertiser_id,
                        db=db,
                        reservation_context={
                            "platform": platform,
                            "conversion_id": normalized_data.get("conversion_id") or "",
                            "event_name": normalized_data.get("event_name") or "default",
                        },
                    )
                )
            except Exception as cap_error:
                # CapChecker/increment_cap_count 已按实际预留回退 Redis，此处勿再全量 DECR
                await db.rollback()
                logger.error(
                    "Cap 计数递增异常，已回滚：error_type=%s",
                    type(cap_error).__name__,
                )
                return {
                    "success": False,
                    "message": "Cap 计数更新失败，转化未入库",
                    "retryable": True,
                }

            if not cap_incremented and cap_status == "cap_check_error":
                await db.rollback()
                logger.error(
                    "Cap 基础设施失败，拒绝入库：offer_id=%s publisher_id=%s",
                    offer_id,
                    publisher_id,
                )
                return {
                    "success": False,
                    "message": "Cap 检查失败，请重试",
                    "retryable": True,
                }

            if not cap_incremented:
                # 真超限：ORM 已 refresh，按 CapExceeded 入库（0 金额 + 关短链）
                cap_ok = False
                pipe_ctx.cap_ok = False
                pipe_ctx.conversion_status = conversion_status_for_cap(False)
                pipe_ctx.final_payout = Decimal("0")
                final_payout = Decimal("0")
                logger.warning(
                    "Cap 预留失败（已超限），按 CapExceeded 入库：offer_id=%s publisher_id=%s",
                    offer_id,
                    publisher_id,
                )
                if offer_id and publisher_id:
                    await deactivate_short_links_on_cap_exceeded(db, offer_id, publisher_id)
            else:
                pipe_ctx.cap_ok = True
                pipe_ctx.conversion_status = "Pending"
                logger.info("Cap 预留成功：offer_id=%s publisher_id=%s", offer_id, publisher_id)

            logger.info("=== 第 8 步：保存转化记录 ====")
            try:
                conversion = await step_save_conversion(pipe_ctx)
            except IntegrityError:
                # 先回滚失败事务，再按正式事件唯一键核验；不能把外键/其他唯一约束错误误报为重复。
                await db.rollback()
                # 先撤销本次预留，再做只读重复核验；避免核验查询自身失败时留下可回滚的 Redis 预留。
                if cap_reservations:
                    cap_rollback_attempted = True
                    await CapChecker.rollback_reservations(cap_reservations)
                is_duplicate_event = await PostbackProcessor._conversion_event_exists(
                    db=db,
                    platform=platform,
                    conversion_id=normalized_data.get("conversion_id") or "",
                    event_name=normalized_data.get("event_name") or "default",
                )
                if not is_duplicate_event:
                    logger.error(
                        "转化保存触发非重复事件 IntegrityError，已回滚：platform=%s event_name=%s",
                        platform,
                        normalized_data.get("event_name"),
                    )
                    raise
                logger.info(
                    "并发重复转化，已跳过：platform=%s event_name=%s",
                    platform,
                    normalized_data.get("event_name"),
                )
                return {
                    "success": True,
                    "message": "重复转化，已跳过",
                }
            except Exception as save_err:
                await db.rollback()
                if cap_reservations:
                    cap_rollback_attempted = True
                    await CapChecker.rollback_reservations(cap_reservations)
                logger.error("保存转化记录失败，已回滚：error_type=%s", type(save_err).__name__)
                raise
            logger.info(
                f"转化记录保存成功：ID={conversion.id}"
            )

            # 转发任务与转化记录在同一事务入队，避免提交后进程崩溃造成首次转发丢失。
            should_forward_pub = bool(
                cap_ok
                and not pipe_ctx.skip_save_and_forward
                and click_association
                and click_association.get("publisher_id")
            )
            should_forward_prod = bool(
                cap_ok
                and not pipe_ctx.skip_save_and_forward
                and conversion.product_id
            )
            queued_forwards = await PostbackProcessor._enqueue_downstream_forward_tasks(
                db=db,
                conversion=conversion,
                click_association=click_association,
                forward_publisher=should_forward_pub,
                forward_product=should_forward_prod,
            )

            # 第三方事件 Outbox 与转化、Cap、下游队列同一事务提交，封闭 commit 后进程崩溃漏报窗口。
            third_party_report_outbox_id = await PostbackProcessor._enqueue_third_party_report_if_needed(
                platform=platform,
                click_association=click_association,
                normalized_data=normalized_data,
                db=db,
            )

            # ========== 第 11 步：提交事务（Cap / 短链 / 转化 / 转发队列 / 第三方 Outbox 原子提交） ==========
            logger.info("=== 第 11 步：提交事务 ====")
            cap_commit_reconciliation_started = True
            await PostbackProcessor._commit_conversion_with_cap_reconciliation(
                db=db,
                conversion_id=conversion.id,
                cap_reservations=cap_reservations,
            )
            logger.info("事务提交成功")

            # 立即触发仅作为低延迟优化；真正的恢复依赖数据库队列和每分钟定时任务。
            if queued_forwards:
                try:
                    from app.scheduler_module.tasks.forward_tasks import trigger_forward_processing

                    asyncio.create_task(trigger_forward_processing())
                except RuntimeError:
                    logger.warning(
                        "当前无可用事件循环，首次转发由持久化队列定时任务接管"
                    )

            # 提交后立即尝试消费 Outbox 仅作为低延迟优化；进程崩溃时由每分钟调度任务恢复。
            if third_party_report_outbox_id:
                try:
                    asyncio.get_running_loop().create_task(
                        process_postback_report_outbox(
                            batch_size=1,
                            report_log_id=third_party_report_outbox_id,
                        )
                    )
                except RuntimeError:
                    logger.warning(
                        "当前无可用事件循环，第三方 Report Outbox 将由持久化调度任务接管：id=%s",
                        third_party_report_outbox_id,
                    )
            
            logger.info(
                "持久化下游转发任务已入队：conversion_record_id=%s queued=%s",
                conversion.id,
                queued_forwards,
            )

            # ========== 第 10 步：通知发送 ==========
            logger.info("=== 第 10 步：通知发送 ====")
            try:
                await PostbackNotifier.notify_conversion(conversion, db)
                logger.info("通知发送完成")
            except Exception as e:
                logger.warning("通知发送失败：error_type=%s", type(e).__name__)
            
            # ========== 完成 ==========
            logger.info("=== PostBack 处理完成 ===")
            logger.info(
                f"Postback 处理完成：platform={platform}, "
                f"conversion_id={conversion.id}, payout={final_payout}"
            )
            
            return {
                "success": True,
                "message": "PostBack 接收成功",
                "conversion_id": conversion.id,
                "platform": platform,
                "payout": final_payout
            }
        except Exception as e:
            # COMMIT 前若异常发生在转化保存/队列入队等步骤，回退本次已成功预留的 Redis Cap。
            # COMMIT reconciliation 已启动时由其自行判断数据库提交结果，禁止外层重复 DECR。
            if cap_reservations and not cap_rollback_attempted and not cap_commit_reconciliation_started:
                cap_rollback_attempted = True
                try:
                    await CapChecker.rollback_reservations(cap_reservations)
                except Exception:
                    logger.critical(
                        "Postback 在 COMMIT 前异常，Cap reservation 回退失败，需对账：reservation_count=%s",
                        len(cap_reservations),
                    )
            # 发生异常时回滚数据库事务
            try:
                await db.rollback()
            except Exception:
                logger.error("Postback 异常后的数据库回滚失败")
            logger.error("Postback 处理失败，已回滚事务：platform=%s error_type=%s", platform, type(e).__name__)
            raise
    
    @staticmethod
    async def _commit_conversion_with_cap_reconciliation(
        *,
        db: AsyncSession,
        conversion_id: int,
        cap_reservations: list[tuple],
    ) -> None:
        """
        提交转化与队列事务；遇到提交异常时先查询提交结果，再决定是否回退 Redis。

        数据库连接在 COMMIT 响应期间断开时，提交结果可能未知。只有确认转化不存在才回退
        本次 Redis reservation，避免「DB 已提交但 Redis 被回退」导致 Cap 超卖。
        """
        try:
            # 在 DB COMMIT 前续租，避免恢复 Worker 抢占仍在执行中的 Postback reservation。
            for reservation in cap_reservations or []:
                ledger_key = reservation[5] if len(reservation) > 5 else None
                lease_owner = reservation[6] if len(reservation) > 6 else None
                if ledger_key and lease_owner:
                    await CapReservationLedger.renew_lease(ledger_key, lease_owner)
            await db.commit()
            # DB 转化事务已提交后再独立确认账本；失败时保留活动状态，由恢复 Worker 按正式事件键修复。
            for reservation in cap_reservations or []:
                ledger_key = reservation[5] if len(reservation) > 5 else None
                lease_owner = reservation[6] if len(reservation) > 6 else None
                if ledger_key:
                    try:
                        await CapReservationLedger.finalize(
                            ledger_key, "COMMITTED", lease_owner=lease_owner
                        )
                    except Exception as ledger_error:
                        logger.critical(
                            "转化已提交但 Cap Reservation 账本终态更新失败，等待恢复：error_type=%s",
                            type(ledger_error).__name__,
                        )
            return
        except Exception as commit_error:
            try:
                await db.rollback()
            except Exception as rollback_error:
                logger.critical(
                    "Postback COMMIT 异常后 DB rollback 也失败；保留 Redis Cap reservation：error_type=%s",
                    type(rollback_error).__name__,
                )
                raise commit_error

            try:
                result = await db.execute(
                    select(PostbackConversion.id)
                    .where(PostbackConversion.id == conversion_id)
                    .limit(1)
                )
                committed = result.scalar_one_or_none() is not None
            except Exception as lookup_error:
                logger.critical(
                    "Postback COMMIT 结果无法确认；为避免 Cap 超卖，保留 Redis reservation：error_type=%s",
                    type(lookup_error).__name__,
                )
                raise commit_error

            if not committed and cap_reservations:
                try:
                    await CapChecker.rollback_reservations(cap_reservations)
                except Exception as rollback_error:
                    logger.critical(
                        "Postback COMMIT 确认未提交，但 Redis Cap reservation 回退失败：error_type=%s",
                        type(rollback_error).__name__,
                    )
            elif committed:
                # COMMIT 响应丢失但正式转化已存在：保留 Redis 计数并补记账本终态。
                for reservation in cap_reservations or []:
                    ledger_key = reservation[5] if len(reservation) > 5 else None
                    lease_owner = reservation[6] if len(reservation) > 6 else None
                    if ledger_key:
                        try:
                            await CapReservationLedger.finalize(
                                ledger_key, "COMMITTED", lease_owner=lease_owner
                            )
                        except Exception as ledger_error:
                            logger.critical(
                                "正式转化已存在但 Reservation 账本无法标记 COMMITTED：error_type=%s",
                                type(ledger_error).__name__,
                            )
                logger.critical(
                    "Postback COMMIT 返回异常但 DB 已确认转化存在；保留 Redis Cap reservation"
                )
            raise commit_error

    @staticmethod
    async def _enqueue_downstream_forward_tasks(
        *,
        db: AsyncSession,
        conversion: PostbackConversion,
        click_association: Optional[Dict[str, Any]],
        forward_publisher: bool,
        forward_product: bool,
    ) -> int:
        """在转化事务中写入首次下游转发任务，保证提交后可由 Scheduler 恢复。"""
        queued = 0
        now = get_app_now_naive()

        if forward_publisher:
            publisher_id = (click_association or {}).get("publisher_id")
            if publisher_id:
                result = await db.execute(
                    select(Publisher).where(Publisher.id == publisher_id).limit(1)
                )
                publisher = result.scalars().first()
                if publisher and publisher.is_active and publisher.postback_url:
                    db.add(
                        PostbackForwardQueue(
                            conversion_id=conversion.id,
                            product_id=None,
                            publisher_id=publisher_id,
                            downstream_url=publisher.postback_url,
                            request_method=publisher.postback_method or "GET",
                            request_params=None,
                            request_data=None,
                            retry_count=0,
                            next_retry_time=now,
                        )
                    )
                    queued += 1

        if forward_product and conversion.product_id:
            result = await db.execute(
                select(Product).where(Product.id == conversion.product_id).limit(1)
            )
            product = result.scalars().first()
            if product and product.is_active and product.downstream_postback_url:
                db.add(
                    PostbackForwardQueue(
                        conversion_id=conversion.id,
                        product_id=conversion.product_id,
                        publisher_id=None,
                        downstream_url=product.downstream_postback_url,
                        request_method=product.downstream_postback_method or "GET",
                        request_params=None,
                        request_data=None,
                        retry_count=0,
                        next_retry_time=now,
                    )
                )
                queued += 1

        if queued:
            await db.flush()
            logger.info(
                "已在转化事务中写入下游转发队列：conversion_id=%s count=%s",
                conversion.id,
                queued,
            )
        return queued

    @staticmethod
    async def _enqueue_third_party_report_if_needed(
        *,
        platform: str,
        click_association: Optional[Dict[str, Any]],
        normalized_data: Dict[str, Any],
        db: AsyncSession,
    ) -> Optional[int]:
        """在转化主事务中持久化第三方上报 Outbox，不在请求线程直接发送网络请求。"""
        if not click_association:
            return None

        raw_url_params = click_association.get("url_params")
        if isinstance(raw_url_params, dict):
            url_params = raw_url_params
        elif isinstance(raw_url_params, str):
            url_params = parse_stored_url_params(raw_url_params)
        else:
            url_params = {}

        click_id = click_association.get("click_id")
        ip = click_association.get("ip")
        ua = click_association.get("user_agent")
        fbclid = scalar_query_value(url_params.get("fbclid"))
        dp = resolve_dp_from_url_params(url_params)
        email = scalar_query_value(url_params.get("email"))
        phone = scalar_query_value(url_params.get("phone"))

        if not fbclid and not dp:
            logger.debug("未检测到 fbclid/dp，不创建第三方 Report Outbox")
            return None

        cloak_cfg_pb = None
        if dp:
            result = await db.execute(
                select(CloakConfig).where(CloakConfig.cloak_name == str(dp).strip())
            )
            cloak_cfg_pb = result.scalars().first()

        short_link_id = click_association.get("short_link_id")
        short_code = click_association.get("short_code")
        if short_link_id:
            short_link = await db.scalar(
                select(ShortLink).where(ShortLink.id == short_link_id).limit(1)
            )
            if short_link and short_link.short_code:
                short_code = short_link.short_code

        amount_raw = normalized_data.get("payout")
        try:
            amount_decimal = Decimal(str(amount_raw))
            amount = (
                amount_decimal
                if amount_decimal.is_finite() and amount_decimal >= 0
                else Decimal("0")
            )
        except (InvalidOperation, ValueError, TypeError):
            amount = Decimal("0")

        use_cfg_pb = bool(
            cloak_cfg_pb
            and getattr(cloak_cfg_pb, "is_enabled", False)
            and getattr(cloak_cfg_pb, "postback_report_enabled", False)
        )
        if use_cfg_pb:
            fb_event = (cloak_cfg_pb.postback_report_event or "Purchase").strip() or "Purchase"
            cur_send = (cloak_cfg_pb.postback_report_currency or "USD").strip().upper() or "USD"
            fixed_val = getattr(cloak_cfg_pb, "postback_report_value", None)
            try:
                fixed_val = Decimal(str(fixed_val)) if fixed_val is not None else None
            except (TypeError, ValueError, InvalidOperation):
                fixed_val = None
            if fb_event == "Purchase":
                amt_send = fixed_val if fixed_val is not None and fixed_val > 0 else amount
            else:
                amt_send = None
                cur_send = None
        else:
            fb_event = "Purchase"
            cur_send = "USD"
            amt_send = amount

        if fb_event == "Purchase" and (amt_send is None or amt_send <= 0):
            logger.warning("Purchase 金额无效，不创建第三方 Report Outbox")
            return None

        report_adsid = fbclid or (
            scalar_query_value(url_params.get("click_id"))
            or scalar_query_value(url_params.get("cid"))
            or (str(click_id).strip() if click_id else None)
            or (
                str(normalized_data.get("conversion_id")).strip()
                if normalized_data.get("conversion_id")
                else None
            )
        )
        if not report_adsid:
            logger.warning("缺少可用 adsid，不创建第三方 Report Outbox")
            return None

        conversion_id = str(normalized_data.get("conversion_id") or "").strip()
        if not conversion_id:
            # 正常 DataValidator 应拒绝无稳定事件 ID；这里再做一道防御。
            raise ValueError("第三方 Report Outbox 缺少稳定 conversion_id")

        outbox_id = await enqueue_postback_report(
            db,
            platform=platform,
            adsid=report_adsid,
            event=fb_event,
            conversion_id=conversion_id,
            email=email,
            ip=ip,
            phone=phone,
            ua=ua,
            currency=cur_send,
            amount=amt_send,
            short_link_id=int(short_link_id) if short_link_id else None,
            cloak_name=str(dp).strip() if dp else None,
            short_code=str(short_code).strip() if short_code else None,
            click_time=click_association.get("click_time"),
        )
        logger.info(
            "第三方 Report Outbox 已写入转化事务：id=%s event=%s",
            outbox_id,
            fb_event,
        )
        return outbox_id

    @staticmethod
    async def _handle_ip_failure(
        platform: str,
        raw_data: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        处理 IP 验证失败
        
        Args:
            platform: 平台名称
            raw_data: 原始数据
            db: 数据库会话
        
        Returns:
            处理结果
        """
        conversion_id_hint = (
            raw_data.get("clk_id")
            or raw_data.get("conversion_id")
            or raw_data.get("click_id")
            or "unknown"
        )
        
        # 发送管理员通知
        try:
            admin_config_result = await db.execute(
                select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
            )
            admin_config = admin_config_result.scalars().first()
            
            if (
                admin_config
                and admin_config.telegram_enabled
                and admin_config.notify_system_errors
                and admin_config.telegram_chat_id
            ):
                msg_lines = [
                    "⚠️ Postback IP 验证失败",
                    "",
                    f"平台：{platform}",
                    "转化 ID/点击 ID: [已省略]",
                    "说明：IP 为空或无法获取，已拒绝处理（不入库、不转发）。"
                ]
                
                await TelegramNotificationService.send_admin_notification(
                    message="\n".join(msg_lines),
                    telegram_chat_id=admin_config.telegram_chat_id,
                    notification_type='system_error',
                    db=db,
                    commit=False,
                )
        except Exception as e:
            logger.warning("发送 IP 验证失败通知失败：error_type=%s", type(e).__name__)

        try:
            await db.commit()
        except Exception as e:
            logger.warning("提交 IP 失败通知记录失败：error_type=%s", type(e).__name__)
            await db.rollback()
        
        return {
            "success": True,
            "message": "PostBack 接收成功（IP 验证失败，未记录）",
            "conversion_id": conversion_id_hint,
            "platform": platform,
            "is_test_data": True
        }

