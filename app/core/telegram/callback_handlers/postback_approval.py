"""
Postback 审批回调处理器

处理管理员对 Postback 待确认转化的批准/拒绝操作（python-telegram-bot）。
"""
import logging
import threading

logger = logging.getLogger(__name__)

from app.core.utils import get_app_now_naive
from app.core.telegram.sync_db import get_sync_session_factory


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


def _api(chat_id: int, coro):
    """后台线程内走发送互斥。"""
    from app.core.telegram.message_sender import call_telegram_api_throttled

    return call_telegram_api_throttled(coro, chat_id=str(chat_id))


def process_pending_conversion(
    pending_id: int,
    action: str,
    callback_query_id: str,
    chat_id: int,
    message_id: int,
):
    """处理待确认转化记录（同步操作，在后台线程执行）。"""
    from app.core.config import settings
    from app.core.telegram.ptb_runtime import get_send_bot
    from sqlalchemy import select as sync_select
    from app.models.models import PendingPostbackConversion, PostbackConversion, Click
    from app.core.tracking.click_token import resolve_click_from_token

    token = getattr(settings, "TELEGRAM_TOKEN", None)
    if not token:
        logger.error("[回调查询处理器] TELEGRAM_TOKEN 未配置")
        return
    bot = get_send_bot(str(token).strip())

    SessionLocal = get_sync_session_factory()

    try:
        with SessionLocal() as db:
            result = db.execute(
                sync_select(PendingPostbackConversion).where(
                    PendingPostbackConversion.id == pending_id,
                    PendingPostbackConversion.status == "pending",
                )
            )
            pending = result.scalar_one_or_none()

            if not pending:
                try:
                    _api(
                        chat_id,
                        bot.answer_callback_query(
                            callback_query_id=callback_query_id,
                            text="记录不存在或已被处理",
                        ),
                    )
                except Exception as e:
                    logger.warning("发送回调确认时出错：error_type=%s", type(e).__name__)
                return

            if action == "approve":
                # 与 PostbackPendingService 保持一致：批准前检查正式记录，防止 Telegram
                # 回调路径绕过幂等保护重复创建同一转化。
                existing_conversion_id = db.execute(
                    sync_select(PostbackConversion.id)
                    .where(
                        PostbackConversion.platform == pending.platform,
                        PostbackConversion.conversion_id == pending.conversion_id,
                        PostbackConversion.event_name == pending.event_name,
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if existing_conversion_id is not None:
                    pending.status = "approved"
                    pending.approved_at = get_app_now_naive()
                    db.commit()
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
                    # 审批转正式记录时保留点击关联，并补齐归因快照，避免后续筛选依赖回退查询。
                    click_id=pending.click_id,
                    click_time=click_time,
                    offer_id=offer_id,
                    publisher_id=publisher_id,
                    advertiser_id=advertiser_id,
                    conversion_status="Pending",
                    raw_data=pending.raw_data,
                    created_at=get_app_now_naive(),
                )
                db.add(conversion)
                pending.status = "approved"
                pending.approved_at = get_app_now_naive()
                db.commit()
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
                pending.status = "rejected"
                pending.rejected_at = get_app_now_naive()
                db.commit()

                try:
                    _api(
                        chat_id,
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=(
                                f"❌ 已拒绝转化记录\n\n"
                                f"转化 ID: {pending.conversion_id}\n"
                                f"平台：{pending.platform}\n"
                                f"IP: {pending.request_ip}"
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
        logger.error("处理待确认转化记录失败：error_type=%s", type(e).__name__)
        try:
            _api(
                chat_id,
                bot.answer_callback_query(
                    callback_query_id=callback_query_id,
                    text="处理失败，请稍后重试",
                ),
            )
        except Exception as err:
            logger.warning("发送回调确认时出错：error_type=%s", type(err).__name__)


async def handle_postback_approval(update, context):
    """处理 Postback 待确认转化的确认/拒绝回调。"""
    query = update.callback_query
    if not query or not query.message or not query.data:
        return

    user = query.from_user
    chat_type = getattr(getattr(query.message, "chat", None), "type", None)
    if not _is_authorized_admin(getattr(user, "id", None), chat_type):
        logger.warning(
            "拒绝未授权 Telegram Postback 审批操作：user_id=%s chat_type=%s",
            getattr(user, "id", None),
            chat_type,
        )
        try:
            await query.answer(text="无权限执行此操作", show_alert=True)
        except Exception as exc:
            logger.warning("发送未授权回调提示失败：error_type=%s", type(exc).__name__)
        return

    logger.info(
        f"[回调查询处理器] 收到管理员回调：callback_data='{query.data}', "
        f"user_id={getattr(user, 'id', None)}"
    )

    try:
        action = "approve" if query.data.startswith("postback_approve_") else "reject"
        pending_id = int(query.data.split("_")[-1])
        callback_query_id = query.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id

        try:
            await query.answer(text="正在处理，请稍候...", show_alert=False)
        except Exception as e:
            logger.warning("确认 Telegram 回调失败：error_type=%s", type(e).__name__)

        thread = threading.Thread(
            target=process_pending_conversion,
            args=(pending_id, action, callback_query_id, chat_id, message_id),
            daemon=True,
        )
        thread.start()
    except Exception as e:
        logger.error("处理回调失败：error_type=%s", type(e).__name__)
