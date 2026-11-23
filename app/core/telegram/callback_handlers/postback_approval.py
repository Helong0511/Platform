"""
Postback 审批回调处理器

处理管理员对 Postback 待确认转化的批准/拒绝操作（python-telegram-bot）。
"""
import asyncio
import logging

from app.core.telegram_utils import mask_telegram_chat_id
import re

logger = logging.getLogger(__name__)

from app.core.utils import get_app_now_naive
from app.core.telegram.sync_db import get_sync_session_factory
from app.core.postback.pending_lock import build_pending_for_update_statement
from app.core.postback.approval_audit import add_postback_approval_audit
from app.core.postback.transformers.normalizer import normalize_event_name
from app.core.postback.savers.conversion_saver import sanitize_postback_raw_data


def _is_authorized_admin(user_id: int | None, chat_type: str | None) -> bool:
    """
    验证 Telegram 回调操作者身份。

    优先使用显式 TELEGRAM_ADMIN_USER_IDS；未配置时仅兼容私聊场景，
    此时 TELEGRAM_ADMIN 中的私聊 Chat ID 与操作者 User ID 相同。
    群聊必须配置独立用户白名单，不能把群 Chat ID 当作授权主体。
    """
    if user_id is None:
        return False

    from app.core.config import settings

    configured_user_ids = getattr(settings, "TELEGRAM_ADMIN_USER_IDS", None)
    if configured_user_ids:
        allowed_user_ids = {
            item.strip()
            for item in str(configured_user_ids).split(",")
            if item.strip()
        }
        return str(user_id) in allowed_user_ids

    if chat_type != "private":
        return False

    admin_chat_ids = getattr(settings, "TELEGRAM_ADMIN", None) or ""
    legacy_private_ids = {
        item.strip()
        for item in str(admin_chat_ids).split(",")
        if item.strip() and item.strip().isdigit()
    }
    return str(user_id) in legacy_private_ids


def _parse_approval_callback_data(value: str) -> tuple[str, int] | None:
    """严格解析审批按钮数据，未知前缀不得被误判为拒绝操作。"""
    match = re.fullmatch(r"postback_(approve|reject)_([1-9][0-9]{0,9})", str(value or ""))
    if not match:
        return None
    pending_id = int(match.group(2))
    if pending_id > 2_147_483_647:
        return None
    return match.group(1), pending_id


def _api(chat_id: int, coro):
    """后台线程内走发送互斥。"""
    from app.core.telegram.message_sender import call_telegram_api_throttled

    return call_telegram_api_throttled(coro, chat_id=str(chat_id))


def _build_rejection_message(conversion_id: str, platform: str) -> str:
    """构建拒绝审批通知；不向 Telegram 聊天发送来源 IP 等个人信息。"""
    return (
        "❌ 已拒绝转化记录\n\n"
        f"转化 ID: {conversion_id}\n"
        f"平台：{platform}"
    )


def process_pending_conversion(
    pending_id: int,
    action: str,
    callback_query_id: str,
    chat_id: int,
    message_id: int,
    actor_telegram_user_id: int | None = None,
    fallback_bot=None,
    callback_loop=None,
):
    """处理待确认转化记录（同步操作，在后台线程执行）。"""
    if action not in {"approve", "reject"}:
        logger.warning("拒绝未知 Telegram Postback 审批动作")
        return

    bot = None
    business_committed = False
    try:
        from app.core.config import settings
        from app.core.telegram.ptb_runtime import get_send_bot
        from sqlalchemy import select as sync_select
        from app.models.models import (
            PendingPostbackConversion,
            PostbackConversion,
            Click,
            TelegramPostbackApprovalAudit,
        )
        from app.core.tracking.click_token import resolve_click_from_token

        token = getattr(settings, "TELEGRAM_TOKEN", None)
        if not token:
            raise RuntimeError("Telegram token is not configured")
        bot = get_send_bot(str(token).strip())

        SessionLocal = get_sync_session_factory()


        with SessionLocal() as db:
            result = db.execute(
                build_pending_for_update_statement(
                    PendingPostbackConversion, pending_id, status=None
                )
            )
            pending = result.scalar_one_or_none()

            # callback_query_id 是 Telegram 对单次按钮回调的唯一标识。
            # 已存在时记录一次独立的重复尝试，不复用唯一 callback ID。
            prior_callback = db.execute(
                sync_select(TelegramPostbackApprovalAudit.id)
                .where(
                    TelegramPostbackApprovalAudit.telegram_callback_query_id
                    == callback_query_id
                )
                .limit(1)
                .with_for_update()
            ).scalar_one_or_none()
            if prior_callback is not None:
                add_postback_approval_audit(
                    db,
                    pending_conversion_id=pending_id,
                    conversion_id=None,
                    actor_type="telegram",
                    actor_id=actor_telegram_user_id,
                    source="telegram",
                    action=action,
                    outcome="duplicate_callback",
                    previous_status=None,
                    new_status=None,
                )
                db.commit()
                business_committed = True
                try:
                    _api(
                        chat_id,
                        bot.answer_callback_query(
                            callback_query_id=callback_query_id,
                            text="该回调已处理，请刷新记录状态",
                        ),
                    )
                except Exception as e:
                    logger.warning("发送重复回调提示失败：error_type=%s", type(e).__name__)
                return

            if not pending:
                add_postback_approval_audit(
                    db,
                    pending_conversion_id=pending_id,
                    conversion_id=None,
                    actor_type="telegram",
                    actor_id=actor_telegram_user_id,
                    source="telegram",
                    action=action,
                    outcome="not_found",
                    previous_status=None,
                    new_status=None,
                    telegram_callback_query_id=callback_query_id,
                )
                db.commit()
                business_committed = True
                try:
                    _api(
                        chat_id,
                        bot.answer_callback_query(
                            callback_query_id=callback_query_id,
                            text="记录不存在",
                        ),
                    )
                except Exception as e:
                    logger.warning("发送回调确认时出错：error_type=%s", type(e).__name__)
                return

            if pending.status != "pending":
                add_postback_approval_audit(
                    db,
                    pending_conversion_id=pending_id,
                    conversion_id=None,
                    actor_type="telegram",
                    actor_id=actor_telegram_user_id,
                    source="telegram",
                    action=action,
                    outcome="already_processed",
                    previous_status=pending.status,
                    new_status=pending.status,
                    telegram_callback_query_id=callback_query_id,
                )
                db.commit()
                business_committed = True
                try:
                    _api(
                        chat_id,
                        bot.answer_callback_query(
                            callback_query_id=callback_query_id,
                            text=f"记录已处理，当前状态：{pending.status}",
                        ),
                    )
                except Exception as e:
                    logger.warning("发送已处理提示失败：error_type=%s", type(e).__name__)
                return

            if action == "approve":
                # 历史待审批行可能 event_name 为 NULL；统一为 default 后再查重和入库。
                event_name = normalize_event_name(pending.event_name)
                pending.event_name = event_name
                # 与 PostbackPendingService 保持一致：批准前检查正式记录，防止 Telegram
                # 回调路径绕过幂等保护重复创建同一转化。
                existing_conversion_id = db.execute(
                    sync_select(PostbackConversion.id)
                    .where(
                        PostbackConversion.platform == pending.platform,
                        PostbackConversion.conversion_id == pending.conversion_id,
                        PostbackConversion.event_name == event_name,
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if existing_conversion_id is not None:
                    previous_status = pending.status
                    pending.status = "approved"
                    pending.approved_at = get_app_now_naive()
                    add_postback_approval_audit(
                        db,
                        pending_conversion_id=pending.id,
                        conversion_id=existing_conversion_id,
                        actor_type="telegram",
                        actor_id=actor_telegram_user_id,
                        source="telegram",
                        action="approve",
                        outcome="already_exists",
                        previous_status=previous_status,
                        new_status=pending.status,
                        telegram_callback_query_id=callback_query_id,
                    )
                    db.commit()
                    business_committed = True
                    try:
                        _api(
                            chat_id,
                            bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=message_id,
                                text="⚠️ 正式转化记录已存在，待确认记录已标记为处理完成，未重复创建。",
                                reply_markup=None,
                            ),
                        )
                        _api(
                            chat_id,
                            bot.answer_callback_query(
                                callback_query_id=callback_query_id,
                                text="正式记录已存在，未重复创建",
                            ),
                        )
                    except Exception as e:
                        logger.warning("更新重复转化提示失败：error_type=%s", type(e).__name__)
                    logger.info(
                        "Telegram 审批发现正式转化已存在：pending_id=%s existing_conversion_id=%s",
                        pending_id,
                        existing_conversion_id,
                    )
                    return

                # 与统一待确认服务保持一致：先解析签名点击令牌，再用数据库点击记录补齐。
                click_assoc = (
                    resolve_click_from_token(pending.click_id)
                    if pending.click_id
                    else None
                ) or {}
                click = None
                if pending.click_id:
                    click = db.execute(
                        sync_select(Click)
                        .where(Click.click_id == str(pending.click_id))
                        .limit(1)
                    ).scalar_one_or_none()

                # 令牌中存在有效归因时优先使用；否则回退数据库点击行。
                offer_id = click_assoc.get("offer_id")
                publisher_id = click_assoc.get("publisher_id")
                advertiser_id = click_assoc.get("advertiser_id")
                if click:
                    offer_id = offer_id if offer_id is not None else click.offer_id
                    publisher_id = (
                        publisher_id if publisher_id is not None else click.publisher_id
                    )
                    advertiser_id = (
                        advertiser_id if advertiser_id is not None else click.advertiser_id
                    )
                click_time = (
                    pending.click_time
                    or click_assoc.get("click_time")
                    or (click.click_time if click else None)
                )

                conversion = PostbackConversion(
                    platform=pending.platform,
                    conversion_id=pending.conversion_id,
                    event_name=event_name,
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
                    # 审批转正式记录时保留点击关联，并补齐归因快照，避免后续筛选依赖回退查询。
                    click_id=pending.click_id,
                    click_time=click_time,
                    offer_id=offer_id,
                    publisher_id=publisher_id,
                    advertiser_id=advertiser_id,
                    conversion_status="Pending",
                    raw_data=(
                        sanitize_postback_raw_data(pending.raw_data)
                        if pending.raw_data is not None
                        else None
                    ),
                    created_at=get_app_now_naive(),
                )
                previous_status = pending.status
                db.add(conversion)
                pending.status = "approved"
                pending.approved_at = get_app_now_naive()
                db.flush()
                add_postback_approval_audit(
                    db,
                    pending_conversion_id=pending.id,
                    conversion_id=conversion.id,
                    actor_type="telegram",
                    actor_id=actor_telegram_user_id,
                    source="telegram",
                    action="approve",
                    outcome="approved",
                    previous_status=previous_status,
                    new_status=pending.status,
                    telegram_callback_query_id=callback_query_id,
                )
                db.commit()
                business_committed = True
                db.refresh(conversion)

                try:
                    _api(
                        chat_id,
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=(
                                f"✅ 已批准并保存转化记录\n\n"
                                f"转化 ID: {conversion.conversion_id}\n"
                                f"平台：{conversion.platform}\n"
                                f"记录 ID: {conversion.id}"
                            ),
                            reply_markup=None,
                        ),
                    )
                except Exception as e:
                    logger.warning("更新 Telegram 消息失败：error_type=%s", type(e).__name__)

                try:
                    _api(
                        chat_id,
                        bot.answer_callback_query(
                            callback_query_id=callback_query_id,
                            text="已批准并保存",
                        ),
                    )
                except Exception as e:
                    logger.warning("发送回调确认时出错：error_type=%s", type(e).__name__)

                logger.info(
                    f"管理员批准了待确认转化记录：pending_id={pending_id}, conversion_id={conversion.id}"
                )
            else:
                previous_status = pending.status
                pending.status = "rejected"
                pending.rejected_at = get_app_now_naive()
                add_postback_approval_audit(
                    db,
                    pending_conversion_id=pending.id,
                    conversion_id=None,
                    actor_type="telegram",
                    actor_id=actor_telegram_user_id,
                    source="telegram",
                    action="reject",
                    outcome="rejected",
                    previous_status=previous_status,
                    new_status=pending.status,
                    telegram_callback_query_id=callback_query_id,
                )
                db.commit()
                business_committed = True
                try:
                    _api(
                        chat_id,
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=_build_rejection_message(
                                conversion_id=pending.conversion_id,
                                platform=pending.platform,
                            ),
                            reply_markup=None,
                        ),
                    )
                except Exception as e:
                    logger.warning("更新 Telegram 消息失败：error_type=%s", type(e).__name__)

                try:
                    _api(
                        chat_id,
                        bot.answer_callback_query(
                            callback_query_id=callback_query_id,
                            text="已拒绝",
                        ),
                    )
                except Exception as e:
                    logger.warning("发送回调确认时出错：error_type=%s", type(e).__name__)

                logger.info(f"管理员拒绝了待确认转化记录：pending_id={pending_id}")

    except Exception as e:
        logger.error(
            "处理 Telegram Postback 审批失败：pending_id=%s committed=%s error_type=%s",
            pending_id,
            business_committed,
            type(e).__name__,
        )
        if bot is not None:
            try:
                # 已提交业务不能误报为审批失败；仅提示消息状态需要刷新。
                final_text = (
                    "审批已完成，但消息更新失败，请刷新记录状态"
                    if business_committed
                    else "处理失败，请稍后重试"
                )
                _api(
                    chat_id,
                    bot.answer_callback_query(
                        callback_query_id=callback_query_id,
                        text=final_text,
                    ),
                )
            except Exception as err:
                logger.warning("发送回调确认时出错：error_type=%s", type(err).__name__)
        elif (
            fallback_bot is not None
            and callback_loop is not None
            and callback_loop.is_running()
        ):
            try:
                # context.bot 属于 PTB 主事件循环，必须回投原事件循环，不能跨线程直接运行其 HTTP 客户端。
                fallback_coro = fallback_bot.answer_callback_query(
                    callback_query_id=callback_query_id,
                    text=(
                        "审批已完成，但消息更新失败，请刷新记录状态"
                        if business_committed
                        else "处理失败，请稍后重试"
                    ),
                )
                future = asyncio.run_coroutine_threadsafe(fallback_coro, callback_loop)
                future.result(timeout=5)
            except Exception as err:
                logger.warning(
                    "通过 PTB 主事件循环发送最终回调失败：error_type=%s",
                    type(err).__name__,
                )
        else:
            logger.error(
                "Telegram 审批初始化失败且没有可用 Bot/事件循环发送最终回调：pending_id=%s",
                pending_id,
            )


async def handle_postback_approval(update, context):
    """处理 Postback 待确认转化的确认/拒绝回调。"""
    query = update.callback_query
    if not query or not query.message or not query.data:
        return

    parsed = _parse_approval_callback_data(query.data)
    if parsed is None:
        try:
            await query.answer(text="无效的审批操作", show_alert=True)
        except Exception as exc:
            logger.warning("发送无效回调提示失败：error_type=%s", type(exc).__name__)
        return

    action, pending_id = parsed
    user = query.from_user
    user_id = getattr(user, "id", None)
    chat_type = getattr(getattr(query.message, "chat", None), "type", None)
    if not _is_authorized_admin(user_id, chat_type):
        logger.warning(
            "拒绝未授权 Telegram Postback 审批操作：user_id=%s chat_type=%s",
            mask_telegram_chat_id(user_id),
            chat_type,
        )
        # 未授权尝试不改变业务记录，使用独立同步事务持久化拒绝事件。
        try:
            SessionLocal = get_sync_session_factory()
            with SessionLocal() as audit_db:
                add_postback_approval_audit(
                    audit_db,
                    pending_conversion_id=pending_id,
                    conversion_id=None,
                    actor_type="telegram",
                    actor_id=user_id,
                    source="telegram",
                    action=action,
                    outcome="denied",
                    previous_status=None,
                    new_status=None,
                    telegram_callback_query_id=query.id,
                )
                audit_db.commit()
        except Exception as audit_exc:
            logger.warning(
                "记录未授权 Telegram 审批审计失败；error_type=%s",
                type(audit_exc).__name__,
            )
        try:
            await query.answer(text="无权限执行此操作", show_alert=True)
        except Exception as exc:
            logger.warning("发送未授权回调提示失败：error_type=%s", type(exc).__name__)
        return

    logger.info(
        "[回调查询处理器] 收到管理员审批回调：action=%s pending_id=%s user_id=%s",
        action,
        pending_id,
        mask_telegram_chat_id(user_id),
    )

    callback_query_id = query.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    from app.core.telegram.approval_worker import submit_approval_task

    submit_result = submit_approval_task(
        pending_id,
        process_pending_conversion,
        pending_id,
        action,
        callback_query_id,
        chat_id,
        message_id,
        user_id,
        getattr(context, "bot", None),
        asyncio.get_running_loop(),
    )
    if submit_result == "duplicate":
        try:
            await query.answer(text="该记录正在处理中，请稍后刷新状态", show_alert=False)
        except Exception as exc:
            logger.warning("发送重复审批提示失败：error_type=%s", type(exc).__name__)
        return
    if submit_result != "submitted":
        try:
            await query.answer(text="审批队列繁忙，请稍后重试", show_alert=True)
        except Exception as exc:
            logger.warning("发送审批队列繁忙提示失败：error_type=%s", type(exc).__name__)
        return

    try:
        await query.answer(text="正在处理，请稍候...", show_alert=False)
    except Exception as exc:
        # 已成功入队，回调确认失败不应取消审批任务；结果仍以数据库状态为准。
        logger.warning("确认 Telegram 回调失败：error_type=%s", type(exc).__name__)
