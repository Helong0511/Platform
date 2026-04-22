"""
Postback 审批回调处理器

处理管理员对 Postback 待确认转化的批准/拒绝操作
"""
import json
import logging
import threading

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.core.utils import get_app_now_naive


def _create_sync_db_engine():
    """
    创建同步数据库引擎（用于 Telegram bot 回调的同步操作）
    
    Returns:
        SessionLocal: 同步数据库会话工厂
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    sync_db_url = settings.SQLALCHEMY_DATABASE_URI
    if "+aiomysql" in sync_db_url:
        sync_db_url = sync_db_url.replace("+aiomysql", "+pymysql")
    elif "+asyncmy" in sync_db_url:
        sync_db_url = sync_db_url.replace("+asyncmy", "+pymysql")
    elif "mysql://" in sync_db_url and "+" not in sync_db_url:
        pass
    else:
        sync_db_url = sync_db_url.replace("mysql://", "mysql+pymysql://")
    
    sync_engine = create_engine(
        sync_db_url,
        pool_pre_ping=True,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_size=5,
        max_overflow=3,
        echo=False
    )
    return sessionmaker(bind=sync_engine)


def process_pending_conversion(pending_id: int, action: str, callback_query_id: str, chat_id: int, message_id: int):
    """
    处理待确认转化记录（同步操作）
    
    Args:
        pending_id: 待确认记录 ID
        action: 操作类型（approve/reject）
        callback_query_id: 回调查询 ID
        chat_id: 聊天 ID
        message_id: 消息 ID
    """
    from app.core.telegram.bot_state import bot
    from sqlalchemy import select as sync_select
    from app.models.models import PendingPostbackConversion, PostbackConversion
    
    SessionLocal = _create_sync_db_engine()
    
    try:
        with SessionLocal() as db:
            # 查询待确认记录
            result = db.execute(
                sync_select(PendingPostbackConversion).where(
                    PendingPostbackConversion.id == pending_id,
                    PendingPostbackConversion.status == 'pending'
                )
            )
            pending = result.scalar_one_or_none()
            
            if not pending:
                try:
                    bot.answer_callback_query(
                        callback_query_id=callback_query_id,
                        text="记录不存在或已被处理"
                    )
                except Exception as e:
                    logger.warning(f"发送回调确认时出错：{e}")
                return
            
            if action == "approve":
                # 批准：创建正式转化记录
                raw_data = json.loads(pending.raw_data) if pending.raw_data else {}
                
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
                
                db.commit()
                db.refresh(conversion)
                
                # 更新 Telegram 消息
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=(
                            f"✅ 已批准并保存转化记录\n\n"
                            f"转化 ID: {conversion.conversion_id}\n"
                            f"平台：{conversion.platform}\n"
                            f"记录 ID: {conversion.id}"
                        ),
                        reply_markup=None
                    )
                except Exception as e:
                    logger.warning(f"更新消息时出错：{e}")
                
                # 发送回调确认
                try:
                    bot.answer_callback_query(
                        callback_query_id=callback_query_id,
                        text="已批准并保存"
                    )
                except Exception as e:
                    logger.warning(f"发送回调确认时出错：{e}")
                
                logger.info(f"管理员批准了待确认转化记录：pending_id={pending_id}, conversion_id={conversion.id}")
                
            else:  # reject
                # 拒绝：只更新状态
                pending.status = 'rejected'
                pending.rejected_at = get_app_now_naive()
                db.commit()
                
                # 更新 Telegram 消息
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=(
                            f"❌ 已拒绝转化记录\n\n"
                            f"转化 ID: {pending.conversion_id}\n"
                            f"平台：{pending.platform}\n"
                            f"IP: {pending.request_ip}"
                        ),
                        reply_markup=None
                    )
                except Exception as e:
                    logger.warning(f"更新消息时出错：{e}")
                
                # 发送回调确认
                try:
                    bot.answer_callback_query(
                        callback_query_id=callback_query_id,
                        text="已拒绝"
                    )
                except Exception as e:
                    logger.warning(f"发送回调确认时出错：{e}")
                
                logger.info(f"管理员拒绝了待确认转化记录：pending_id={pending_id}")
                
    except Exception as e:
        logger.error(f"处理待确认转化记录失败：{str(e)}", exc_info=True)
        try:
            bot.answer_callback_query(
                callback_query_id=callback_query_id,
                text="处理失败，请稍后重试"
            )
        except Exception as e:
            logger.warning(f"发送回调确认时出错：{e}")


def handle_postback_approval(call):
    """
    处理 Postback 待确认转化的确认/拒绝回调
    
    Args:
        call: Telegram 回调查询对象
    """
    from app.core.telegram import bot_state
    bot = bot_state.bot
    bot_initialized = bot_state.bot_initialized
    TELEBOT_AVAILABLE = bot_state.TELEBOT_AVAILABLE
    
    def _check_bot_available() -> bool:
        """检查 Bot 是否可用"""
        return bot_initialized and TELEBOT_AVAILABLE and bot is not None
    
    logger.info(
        f"[回调查询处理器] ✅✅✅ 收到回调查询：callback_data='{call.data}', "
        f"from_user={call.from_user.username or call.from_user.first_name or '未知'}"
    )
    
    if not _check_bot_available():
        logger.error("[回调查询处理器] Bot 未初始化，无法处理回调查询")
        return
    
    try:
        # 解析 callback_data
        action = "approve" if call.data.startswith("postback_approve_") else "reject"
        pending_id = int(call.data.split("_")[-1])
        
        # 保存需要的变量
        callback_query_id = call.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        
        # 立即确认收到回调
        try:
            bot.answer_callback_query(
                callback_query_id=callback_query_id,
                text="正在处理，请稍候...",
                show_alert=False
            )
        except Exception as e:
            logger.warning(f"确认回调时出错：{e}")
        
        # 在独立线程中运行，避免阻塞 Telegram bot
        thread = threading.Thread(
            target=process_pending_conversion,
            args=(pending_id, action, callback_query_id, chat_id, message_id),
            daemon=True
        )
        thread.start()
        
    except Exception as e:
        logger.error(f"处理回调失败：{str(e)}", exc_info=True)
