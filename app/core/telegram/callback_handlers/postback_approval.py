"""
Postback 审批回调处理器

处理管理员对 Postback 待确认转化的批准/拒绝操作（python-telegram-bot）。
"""
import logging
import threading

logger = logging.getLogger(__name__)

from app.core.utils import get_app_now_naive
from app.core.telegram.sync_db import get_sync_session_factory


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
    from app.models.models import PendingPostbackConversion, PostbackConversion

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
                    logger.warning(f"发送回调确认时出错：{e}")
                return

            if action == "approve":
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
                    logger.warning(f"更新消息时出错：{e}")

                try:
                    _api(
                        chat_id,
                        bot.answer_callback_query(
                            callback_query_id=callback_query_id,
                            text="已批准并保存",
                        ),
                    )
                except Exception as e:
                    logger.warning(f"发送回调确认时出错：{e}")

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
                    logger.warning(f"更新消息时出错：{e}")

                try:
                    _api(
                        chat_id,
                        bot.answer_callback_query(
                            callback_query_id=callback_query_id,
                            text="已拒绝",
                        ),
                    )
                except Exception as e:
                    logger.warning(f"发送回调确认时出错：{e}")

                logger.info(f"管理员拒绝了待确认转化记录：pending_id={pending_id}")

    except Exception as e:
        logger.error(f"处理待确认转化记录失败：{str(e)}", exc_info=True)
        try:
            _api(
                chat_id,
                bot.answer_callback_query(
                    callback_query_id=callback_query_id,
                    text="处理失败，请稍后重试",
                ),
            )
        except Exception as err:
            logger.warning(f"发送回调确认时出错：{err}")


async def handle_postback_approval(update, context):
    """处理 Postback 待确认转化的确认/拒绝回调。"""
    query = update.callback_query
    if not query or not query.message or not query.data:
        return

    logger.info(
        f"[回调查询处理器] ✅✅✅ 收到回调查询：callback_data='{query.data}', "
        f"from_user={query.from_user.username or query.from_user.first_name or '未知'}"
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
            logger.warning(f"确认回调时出错：{e}")

        thread = threading.Thread(
            target=process_pending_conversion,
            args=(pending_id, action, callback_query_id, chat_id, message_id),
            daemon=True,
        )
        thread.start()
    except Exception as e:
        logger.error(f"处理回调失败：{str(e)}", exc_info=True)
