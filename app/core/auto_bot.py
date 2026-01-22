#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author    : 贺鉴龙
# @File      : auto_bot.py
# @Time      : 2025/9/18 11:58
# @IDE       : PyCharm
# @Function  :
import os
import time
import asyncio
import traceback
import logging  # 日志记录模块
import re
import threading
import sys
from pathlib import Path
from app.core.config import settings  # 应用配置
from app.core.utils import get_app_now  # 应用时区时间获取函数
from app.core.telegram_utils import truncate_message, MAX_TELEGRAM_MESSAGE_LENGTH

logger = logging.getLogger(__name__)

# 跨平台文件锁支持
HAS_FCNTL = False
HAS_MSVCRT = False

try:
    import fcntl  # Unix/Linux 文件锁
    HAS_FCNTL = True
except ImportError:
    # Windows 使用 msvcrt 实现文件锁
    try:
        import msvcrt
        HAS_MSVCRT = True
    except ImportError:
        logger.warning("无法导入文件锁模块（fcntl/msvcrt），文件锁功能将不可用")
bot = None
bot_initialized = False  # 添加初始化状态标志
_bot_lock_file = None  # Bot 锁文件句柄
_bot_lock_acquired = False  # 是否已获取锁（用于多进程环境）

# 尝试导入 telebot 模块
try:
    import telebot  # pip3 install --upgrade pyTelegramBotAPI
    from telebot import types
    from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup

    TELEBOT_AVAILABLE = True
except ImportError as import_err:
    TELEBOT_AVAILABLE = False
    logger.warning(f"pyTelegramBotAPI 模块未安装，Telegram Bot 功能将不可用。请运行: pip install pyTelegramBotAPI")
    logger.warning(f"导入错误详情: {import_err}")

# 初始化 Telegram Bot（仅在模块可用且启用时）
telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
if not telegram_enabled:
    logger.info("Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）")
    bot_initialized = False
elif TELEBOT_AVAILABLE:
    try:
        logger.info("正在加载 Telegram token...")
        token = getattr(settings, 'TELEGRAM_TOKEN', None) or None
        if token and isinstance(token, str) and token.strip():
            # 初始化 Telegram Bot
            bot = telebot.TeleBot(token=token)
            bot_initialized = True
            logger.info(f"Telegram Bot 初始化成功，token: {token[:4]}****")
        else:
            logger.warning("Telegram token 未设置或为空，Telegram Bot 功能将不可用")
            bot_initialized = False
    except Exception as err:
        bot_initialized = False
        logger.error(f"初始化 Telegram Bot 失败: {err}", exc_info=True)
else:
    logger.info("Telegram Bot 功能已禁用（pyTelegramBotAPI 未安装）")


def _check_bot_available() -> bool:
    """检查 Bot 是否可用"""
    return bot_initialized and TELEBOT_AVAILABLE and bot is not None


# 命令处理器必须在模块级别注册（pyTelegramBotAPI 的要求）
# 这些装饰器会在模块加载时执行，注册到 bot 对象上
if bot_initialized and TELEBOT_AVAILABLE:
    # 命令处理器（优先级高，先注册）
    @bot.message_handler(commands=['id'])
    def get_chat_id(message):
        """处理 /id 命令：返回聊天ID（支持私聊和群组）"""
        chat_type = message.chat.type if hasattr(message.chat, 'type') else '未知'
        is_group = chat_type in ['group', 'supergroup']
        
        # 检查群组中是否包含 Bot 的提及
        bot_mentioned = False
        bot_username = None
        if is_group:
            try:
                bot_info = bot.get_me()
                bot_username = bot_info.username if bot_info else None
                if bot_username:
                    text = message.text or ''
                    if f'@{bot_username}' in text:
                        bot_mentioned = True
                    # 检查 entities
                    if hasattr(message, 'entities') and message.entities:
                        for entity in message.entities:
                            if entity.type == 'mention':
                                mention_text = text[entity.offset:entity.offset + entity.length]
                                if mention_text == f'@{bot_username}':
                                    bot_mentioned = True
                                    break
            except:
                pass
        
        logger.info(f"[命令处理器] ✅✅✅ 收到 /id 命令，来自用户: {message.from_user.username or message.from_user.first_name or '未知'} (Chat ID: {message.chat.id}, Chat Type: {chat_type}, Bot Mentioned: {bot_mentioned})")
        logger.info(f"[命令处理器] 消息对象: {message}")
        logger.info(f"[命令处理器] 消息文本: {message.text}")
        
        if not _check_bot_available():
            logger.error("[命令处理器] Bot 未初始化，无法处理消息")
            return
        
        # 在群组中，如果没有 @botname，记录警告（但继续处理，因为某些情况下仍可工作）
        if is_group and not bot_mentioned and bot_username:
            logger.warning(f"[命令处理器] ⚠️ 群组中的命令没有 @{bot_username}，可能无法响应（Telegram 隐私模式）")
            logger.info(f"[命令处理器] 💡 提示：在群组中使用命令时，请使用 /id@{bot_username} 格式，或直接 @{bot_username} 后发送命令")
        
        try:
            chat_id = message.chat.id
            logger.info(f"[命令处理器] 准备回复，chat_id: {chat_id}, chat_type: {chat_type}")
            
            # 在群组中，回复消息；在私聊中，也可以回复
            if is_group:
                # 群组中回复
                bot.reply_to(message, f"群组ID: {chat_id}\n你的用户ID: {message.from_user.id}")
            else:
                # 私聊中回复
                bot.reply_to(message, f"你的聊天ID是: {chat_id}")
            
            logger.info(f"[命令处理器] ✅✅✅ 成功回复 /id 命令，聊天ID: {chat_id}")
        except Exception as e:
            logger.error(f"[命令处理器] ❌ 处理 /id 命令时发生错误: {e}", exc_info=True)
            try:
                bot.reply_to(message, "处理命令时发生错误，请稍后重试")
            except:
                pass
    
    # 添加通用消息处理器用于调试（放在命令处理器之后，优先级较低）
    # 注意：命令处理器会优先匹配，这个处理器只处理非命令消息
    @bot.message_handler(func=lambda message: message.text and not message.text.startswith('/'), content_types=['text'])
    def handle_all_messages(message):
        """处理所有非命令文本消息（用于调试）"""
        try:
            text = message.text or ""
            # 使用 INFO 级别确保日志可见
            logger.info(f"[消息接收] ✅ 收到非命令消息: {text[:50]}... 来自用户: {message.from_user.username or message.from_user.first_name or '未知'} (Chat ID: {message.chat.id})")
        except Exception as e:
            logger.error(f"[消息接收] ❌ 处理消息时出错: {e}", exc_info=True)
    
    # 添加一个捕获所有消息的处理器（最低优先级，用于调试）
    @bot.message_handler(func=lambda message: True)
    def handle_any_message(message):
        """捕获所有消息（用于调试，最低优先级）"""
        try:
            text = getattr(message, 'text', '') or ''
            logger.info(f"[调试] 🔍 收到任何类型的消息: {text[:30] if text else '非文本'} (Chat ID: {message.chat.id}, 类型: {type(message).__name__})")
        except Exception as e:
            logger.error(f"[调试] ❌ 处理消息时出错: {e}", exc_info=True)

    @bot.message_handler(commands=['test'])
    def handle_test_command(message):
        """处理 /test 命令：显示测试内联按钮"""
        chat_type = message.chat.type if hasattr(message.chat, 'type') else '未知'
        is_group = chat_type in ['group', 'supergroup']
        logger.info(f"收到 /test 命令，来自用户: {message.from_user.username or message.from_user.first_name or '未知'} (Chat Type: {chat_type})")
        
        if not _check_bot_available():
            logger.error("Bot 未初始化，无法处理消息")
            return

        # 检查群组中是否包含 Bot 的提及
        if is_group:
            try:
                bot_info = bot.get_me()
                bot_username = bot_info.username if bot_info else None
                if bot_username:
                    text = message.text or ''
                    bot_mentioned = f'@{bot_username}' in text
                    if not bot_mentioned:
                        logger.warning(f"⚠️ 群组中的命令没有 @{bot_username}，可能无法响应（Telegram 隐私模式）")
            except:
                pass

        chat_id = message.chat.id
        markup = InlineKeyboardMarkup()

        # 第一行：三个按钮
        markup.row(
            InlineKeyboardButton(text='选项1', callback_data='Option1'),
            InlineKeyboardButton(text='选项2', callback_data='Option2'),
            InlineKeyboardButton(text='选项3', callback_data='Option3')
        )

        # 第二行：两个按钮
        markup.row(
            InlineKeyboardButton(text='选项4', callback_data='Option4'),
            InlineKeyboardButton(text='选项5', callback_data='Option5')
        )

        # 第三行：一个按钮（查看）
        markup.row(InlineKeyboardButton(text='查看', callback_data='View'))

        # 第四行：一个按钮（取消）
        markup.row(InlineKeyboardButton(text='取消', callback_data='Cancel'))

        bot.send_message(chat_id, "这是测试内联按钮：", reply_markup=markup)

    @bot.message_handler(commands=['clock'])
    def handle_clock_command(message):
        """处理 /clock 命令：显示打卡确认按钮"""
        chat_type = message.chat.type if hasattr(message.chat, 'type') else '未知'
        is_group = chat_type in ['group', 'supergroup']
        logger.info(f"收到 /clock 命令，来自用户: {message.from_user.username or message.from_user.first_name or '未知'} (Chat Type: {chat_type})")
        
        if not _check_bot_available():
            logger.error("Bot 未初始化，无法处理消息")
            return

        # 检查群组中是否包含 Bot 的提及
        if is_group:
            try:
                bot_info = bot.get_me()
                bot_username = bot_info.username if bot_info else None
                if bot_username:
                    text = message.text or ''
                    bot_mentioned = f'@{bot_username}' in text
                    if not bot_mentioned:
                        logger.warning(f"⚠️ 群组中的命令没有 @{bot_username}，可能无法响应（Telegram 隐私模式）")
            except:
                pass

        chat_id = message.chat.id
        markup = InlineKeyboardMarkup()

        markup.row(InlineKeyboardButton(text='打卡', callback_data='clock'))
        markup.row(InlineKeyboardButton(text='取消', callback_data='Cancel'))

        bot.send_message(chat_id, "确认是否要打卡？", reply_markup=markup)
    
    @bot.message_handler(commands=['stats', 'conversion'])
    def handle_stats_command(message):
        """处理 /stats 或 /conversion 命令：显示统计确认按钮"""
        chat_type = message.chat.type if hasattr(message.chat, 'type') else '未知'
        is_group = chat_type in ['group', 'supergroup']
        logger.info(f"收到 /stats 命令，来自用户: {message.from_user.username or message.from_user.first_name or '未知'} (Chat Type: {chat_type})")
        
        if not _check_bot_available():
            logger.error("Bot 未初始化，无法处理消息")
            return

        # 检查群组中是否包含 Bot 的提及
        if is_group:
            try:
                bot_info = bot.get_me()
                bot_username = bot_info.username if bot_info else None
                if bot_username:
                    text = message.text or ''
                    bot_mentioned = f'@{bot_username}' in text
                    if not bot_mentioned:
                        logger.warning(f"⚠️ 群组中的命令没有 @{bot_username}，可能无法响应（Telegram 隐私模式）")
            except:
                pass

        chat_id = message.chat.id
        markup = InlineKeyboardMarkup()

        markup.row(InlineKeyboardButton(text='统计转化', callback_data='stats'))
        markup.row(InlineKeyboardButton(text='取消', callback_data='Cancel'))

        bot.send_message(chat_id, "确认是否要统计转化数据？", reply_markup=markup)
    
    logger.info("Telegram Bot 命令处理器已注册: /id, /test, /clock, /stats, /conversion")
    # 验证处理器是否真的注册了
    try:
        # 检查 bot 的 registered_next_step_handlers 和 message_handlers
        handlers_count = len(bot.message_handlers) if hasattr(bot, 'message_handlers') else 0
        logger.info(f"Bot 消息处理器数量: {handlers_count}")
    except Exception as e:
        logger.warning(f"无法检查消息处理器数量: {e}")
else:
    logger.warning("Bot 未初始化或 TELEBOT_AVAILABLE 为 False，命令处理器未注册")
    logger.warning(f"bot_initialized={bot_initialized}, TELEBOT_AVAILABLE={TELEBOT_AVAILABLE}, bot={bot}")

# 处理按钮点击事件
if bot_initialized and TELEBOT_AVAILABLE:
    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
        """处理内联按钮回调查询"""
        logger.info(f"[回调查询处理器] ✅✅✅ 收到回调查询: callback_data='{call.data}', from_user={call.from_user.username or call.from_user.first_name or '未知'}")
        if not _check_bot_available():
            logger.error("[回调查询处理器] Bot 未初始化，无法处理回调查询")
            return

        try:
            logger.info(f"[回调查询处理器] 处理 callback_data: '{call.data}'")
            
            # 处理 Postback 待确认转化的确认/拒绝
            if call.data.startswith("postback_approve_") or call.data.startswith("postback_reject_"):
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker
                from sqlalchemy import select as sync_select
                from app.models.models import PendingPostbackConversion, PostbackConversion
                from app.core.utils import get_app_now_naive
                from app.core.config import settings
                import json
                
                # 解析 callback_data
                action = "approve" if call.data.startswith("postback_approve_") else "reject"
                pending_id = int(call.data.split("_")[-1])
                
                # 使用同步数据库操作（因为 Telegram bot 回调是同步的）
                def process_pending_conversion_sync():
                    try:
                        # 创建同步数据库引擎（从异步 URI 转换为同步 URI）
                        # 支持多种格式：mysql+aiomysql:// 或 mysql+asyncmy://
                        sync_db_url = settings.SQLALCHEMY_DATABASE_URI
                        if "+aiomysql" in sync_db_url:
                            sync_db_url = sync_db_url.replace("+aiomysql", "+pymysql")
                        elif "+asyncmy" in sync_db_url:
                            sync_db_url = sync_db_url.replace("+asyncmy", "+pymysql")
                        elif "mysql://" in sync_db_url and "+" not in sync_db_url:
                            # 如果已经是 mysql:// 格式，直接使用
                            pass
                        else:
                            # 默认使用 pymysql
                            sync_db_url = sync_db_url.replace("mysql://", "mysql+pymysql://")
                        sync_engine = create_engine(
                            sync_db_url,
                            pool_pre_ping=True,
                            pool_recycle=settings.DB_POOL_RECYCLE,
                            pool_size=5,
                            max_overflow=3,
                            echo=False
                        )
                        SessionLocal = sessionmaker(bind=sync_engine)
                        
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
                                bot.answer_callback_query(
                                    callback_query_id=call.id,
                                    text="记录不存在或已被处理"
                                )
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
                                    click_id=pending.click_id,
                                    click_time=pending.click_time,
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
                                bot.edit_message_text(
                                    chat_id=call.message.chat.id,
                                    message_id=call.message.message_id,
                                    text=f"✅ 已批准并保存转化记录\n\n转化ID: {conversion.conversion_id}\n平台: {conversion.platform}\n记录ID: {conversion.id}",
                                    reply_markup=None
                                )
                                bot.answer_callback_query(
                                    callback_query_id=call.id,
                                    text="已批准并保存"
                                )
                                logger.info(f"管理员批准了待确认转化记录: pending_id={pending_id}, conversion_id={conversion.id}")
                                
                            else:  # reject
                                # 拒绝：只更新状态
                                pending.status = 'rejected'
                                pending.rejected_at = get_app_now_naive()
                                db.commit()
                                
                                # 更新 Telegram 消息
                                bot.edit_message_text(
                                    chat_id=call.message.chat.id,
                                    message_id=call.message.message_id,
                                    text=f"❌ 已拒绝转化记录\n\n转化ID: {pending.conversion_id}\n平台: {pending.platform}\nIP: {pending.request_ip}",
                                    reply_markup=None
                                )
                                bot.answer_callback_query(
                                    callback_query_id=call.id,
                                    text="已拒绝"
                                )
                                logger.info(f"管理员拒绝了待确认转化记录: pending_id={pending_id}")
                                
                    except Exception as e:
                        logger.error(f"处理待确认转化记录失败: {str(e)}", exc_info=True)
                        try:
                            bot.answer_callback_query(
                                callback_query_id=call.id,
                                text="处理失败，请稍后重试"
                            )
                        except:
                            pass
                
                # 在独立线程中运行，避免阻塞 Telegram bot
                thread = threading.Thread(target=process_pending_conversion_sync, daemon=True)
                thread.start()
                return
            
            if call.data == "View":
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="你点击了查看按钮"
                )
            elif call.data == "clock":
                current_time = get_app_now()
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"打卡成功！时间：{current_time.strftime('%Y-%m-%d %H:%M:%S')}（时区: {settings.TIMEZONE}）"
                )
            elif call.data == "stats":
                # 发送处理中消息
                processing_message = bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="正在统计转化数据，请稍候..."
                )
                
                # 在独立线程中处理统计，避免阻塞 Telegram bot
                def process_stats():
                    try:
                        from sqlalchemy import create_engine
                        from sqlalchemy.orm import sessionmaker
                        from sqlalchemy import func, and_, select as sync_select
                        from app.models.models import PostbackConversion, ClickStats
                        from app.core.utils import get_app_now_naive
                        from app.core.config import settings
                        from datetime import datetime, time, timedelta
                        
                        # 创建同步数据库引擎
                        sync_db_url = settings.SQLALCHEMY_DATABASE_URI
                        if "+aiomysql" in sync_db_url:
                            sync_db_url = sync_db_url.replace("+aiomysql", "+pymysql")
                        elif "+asyncmy" in sync_db_url:
                            sync_db_url = sync_db_url.replace("+asyncmy", "+pymysql")
                        
                        sync_engine = create_engine(
                            sync_db_url,
                            pool_pre_ping=True,
                            pool_recycle=settings.DB_POOL_RECYCLE,
                            pool_size=5,
                            max_overflow=3,
                            echo=False
                        )
                        SessionLocal = sessionmaker(bind=sync_engine)
                        
                        with SessionLocal() as db:
                            # 计算当天的开始和结束时间
                            today = get_app_now_naive().date()
                            start_of_day = datetime.combine(today, time.min)
                            end_of_day = datetime.combine(today, time.max)
                            
                            # 计算昨天的开始和结束时间
                            yesterday = today - timedelta(days=1)
                            start_of_yesterday = datetime.combine(yesterday, time.min)
                            end_of_yesterday = datetime.combine(yesterday, time.max)
                            
                            # 查询当天总转化数
                            today_result = db.execute(
                                sync_select(func.count(PostbackConversion.id)).where(
                                    and_(
                                        PostbackConversion.created_at >= start_of_day,
                                        PostbackConversion.created_at <= end_of_day
                                    )
                                )
                            )
                            today_total = today_result.scalar() or 0
                            
                            # 查询昨天总转化数
                            yesterday_result = db.execute(
                                sync_select(func.count(PostbackConversion.id)).where(
                                    and_(
                                        PostbackConversion.created_at >= start_of_yesterday,
                                        PostbackConversion.created_at <= end_of_yesterday
                                    )
                                )
                            )
                            yesterday_total = yesterday_result.scalar() or 0
                            
                            # 查询最近7天总转化数
                            seven_days_ago = today - timedelta(days=6)
                            start_of_seven_days = datetime.combine(seven_days_ago, time.min)
                            
                            seven_days_result = db.execute(
                                sync_select(func.count(PostbackConversion.id)).where(
                                    and_(
                                        PostbackConversion.created_at >= start_of_seven_days,
                                        PostbackConversion.created_at <= end_of_day
                                    )
                                )
                            )
                            seven_days_total = seven_days_result.scalar() or 0
                            
                            # 查询当天各渠道转化数（前10个）
                            click_stats_alias = db.query(ClickStats).subquery()
                            channel_result = db.execute(
                                sync_select(
                                    ClickStats.publisher_id,
                                    func.count(PostbackConversion.id).label('conversion_count')
                                ).join(
                                    PostbackConversion, PostbackConversion.click_id == ClickStats.click_id
                                ).where(
                                    and_(
                                        PostbackConversion.created_at >= start_of_day,
                                        PostbackConversion.created_at <= end_of_day,
                                        ClickStats.publisher_id.isnot(None)
                                    )
                                ).group_by(
                                    ClickStats.publisher_id
                                ).order_by(
                                    func.count(PostbackConversion.id).desc()
                                ).limit(10)
                            )
                            channel_stats = channel_result.all()
                            
                            # 构建统计消息
                            stats_message = "📊 转化统计信息\n\n"
                            stats_message += f"📅 今日统计 ({today.strftime('%Y-%m-%d')})\n"
                            stats_message += f"• 当天总转化个数: {today_total}\n"
                            stats_message += f"• 昨日总转化个数: {yesterday_total}\n"
                            stats_message += f"• 近7天总转化个数: {seven_days_total}\n"
                            
                            if channel_stats:
                                stats_message += "\n📤 今日渠道转化TOP10\n"
                                for i, (publisher_id, count) in enumerate(channel_stats, 1):
                                    stats_message += f"{i}. 渠道ID: {publisher_id} - 转化数: {count}\n"
                            else:
                                stats_message += "\n📤 今日渠道转化\n"
                                stats_message += "• 暂无渠道转化数据\n"
                            
                            # 更新消息
                            bot.edit_message_text(
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                text=stats_message
                            )
                            
                    except Exception as e:
                        logger.error(f"处理转化统计时发生错误: {e}", exc_info=True)
                        try:
                            bot.edit_message_text(
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                text="统计失败，请稍后重试\n\n错误信息: " + str(e)[:100]
                            )
                        except:
                            pass
                
                # 启动线程处理统计
                thread = threading.Thread(target=process_stats, daemon=True)
                thread.start()
            elif call.data == "Cancel":
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="你取消了操作"
                )
                bot.delete_message(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id
                )
            else:
                bot.answer_callback_query(callback_query_id=call.id, text="未知操作")
        except Exception as e:
            logger.error(f"处理回调查询时发生错误: {e}", exc_info=True)
            try:
                bot.answer_callback_query(callback_query_id=call.id, text="处理失败，请稍后重试")
            except Exception:
                pass

if bot_initialized and TELEBOT_AVAILABLE:
    @bot.message_handler(content_types=["photo"])
    def handle_image(message):
        """处理图片消息"""
        if not _check_bot_available():
            logger.error("Bot 未初始化，无法处理消息")
            return

        bot.reply_to(message, "收到图片！")


def run_bot():
    """运行 Bot 轮询（在独立线程中执行）"""
    if not _check_bot_available():
        logger.error("Bot 未初始化，无法启动轮询")
        return

    logger.info(f"[线程: {threading.current_thread().name}] 开始启动 Telegram Bot 轮询...")
    
    try:
        # 先测试 Bot 连接（带重试机制）
        max_retries = 3
        retry_delay = 5  # 秒
        connection_success = False
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"尝试连接 Telegram Bot API (第 {attempt}/{max_retries} 次)...")
                bot_info = bot.get_me()
                logger.info(f"✅ Telegram Bot 连接成功: @{bot_info.username} (ID: {bot_info.id})")
                connection_success = True
                break
            except Exception as test_error:
                error_msg = str(test_error)
                error_type = type(test_error).__name__
                
                # 判断错误类型
                is_network_error = any(keyword in error_msg.lower() for keyword in [
                    'network is unreachable',
                    'connection refused',
                    'connection timeout',
                    'name resolution failed',
                    'failed to establish',
                    'max retries exceeded'
                ])
                
                if is_network_error:
                    logger.warning(f"⚠️ Telegram Bot 连接失败 (第 {attempt}/{max_retries} 次): 网络连接问题")
                    logger.warning(f"   错误类型: {error_type}")
                    logger.warning(f"   错误信息: {error_msg[:200]}")
                    
                    if attempt < max_retries:
                        logger.info(f"   等待 {retry_delay} 秒后重试...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                    else:
                        # 初始连接失败，但继续尝试（网络可能稍后恢复）
                        logger.error("❌ Telegram Bot 初始连接失败: 无法连接到 api.telegram.org")
                        logger.error("   可能的原因:")
                        logger.error("   1. 服务器无法访问 api.telegram.org（防火墙/网络限制）")
                        logger.error("   2. 需要使用代理访问 Telegram API")
                        logger.error("   3. 网络暂时不可用")
                        logger.error("   4. DNS 解析失败")
                        logger.error("   建议:")
                        logger.error("   - 检查服务器网络连接: ping api.telegram.org")
                        logger.error("   - 检查防火墙设置")
                        logger.error("   - 如果在中国大陆，可能需要配置代理")
                        logger.error("   - 检查 DNS 设置")
                        logger.warning("⚠️ 将继续尝试连接，直到网络恢复...")
                        logger.warning("⚠️ Telegram 通知功能暂时不可用，但会在连接恢复后自动启用")
                        
                        # 进入持续重试循环（而不是直接返回）
                        reconnect_delay = 30  # 初始重连延迟30秒
                        max_reconnect_delay = 300  # 最大重连延迟5分钟
                        reconnect_count = 0
                        
                        while True:
                            reconnect_count += 1
                            logger.info(f"🔄 尝试重新连接 Telegram Bot (第 {reconnect_count} 次)...")
                            
                            try:
                                bot_info = bot.get_me()
                                logger.info(f"✅ Telegram Bot 连接成功: @{bot_info.username} (ID: {bot_info.id})")
                                logger.info("✅ 网络连接已恢复，继续启动轮询...")
                                connection_success = True
                                break  # 连接成功，跳出重试循环
                            except Exception as reconnect_error:
                                error_msg = str(reconnect_error)
                                error_type = type(reconnect_error).__name__
                                
                                is_network_error = any(keyword in error_msg.lower() for keyword in [
                                    'network is unreachable',
                                    'connection refused',
                                    'connection timeout',
                                    'name resolution failed',
                                    'failed to establish',
                                    'max retries exceeded'
                                ])
                                
                                if is_network_error:
                                    # 计算指数退避延迟
                                    current_delay = min(reconnect_delay * (2 ** min((reconnect_count - 1) // 5, 4)), max_reconnect_delay)
                                    
                                    if reconnect_count % 5 == 0:  # 每5次记录一次详细日志
                                        logger.warning(f"⚠️ 网络连接仍然失败 (已重试 {reconnect_count} 次)")
                                        logger.warning(f"   将在 {current_delay} 秒后继续尝试...")
                                    else:
                                        logger.debug(f"⚠️ 网络连接失败，{current_delay} 秒后重试...")
                                    
                                    time.sleep(current_delay)
                                else:
                                    # 非网络错误（如 Token 错误），直接返回
                                    logger.error(f"❌ Telegram Bot 连接测试失败: {error_type}")
                                    logger.error(f"   错误信息: {error_msg[:200]}")
                                    logger.error("   请检查 TELEGRAM_TOKEN 是否正确")
                                    return
                        
                        # 如果连接成功，继续执行后续代码
                        if not connection_success:
                            logger.error("❌ 重连循环异常退出")
                            return
                else:
                    # 其他错误（如 Token 错误）
                    logger.error(f"❌ Telegram Bot 连接测试失败: {error_type}")
                    logger.error(f"   错误信息: {error_msg[:200]}")
                    logger.error("   请检查 TELEGRAM_TOKEN 是否正确")
                    return
        
        if not connection_success:
            logger.error("❌ Telegram Bot 连接失败，轮询将不会启动")
            return
        
        # 检查消息处理器
        try:
            handlers_count = len(bot.message_handlers) if hasattr(bot, 'message_handlers') else 0
            logger.info(f"开始轮询前，Bot 消息处理器数量: {handlers_count}")
            if handlers_count == 0:
                logger.warning("警告：没有注册任何消息处理器！命令可能无法工作")
        except Exception as e:
            logger.warning(f"无法检查消息处理器: {e}")
        
        # 检查并删除可能存在的 webhook（webhook 会阻止 polling）
        try:
            webhook_info = bot.get_webhook_info()
            logger.info(f"Webhook 信息: url={webhook_info.url}, pending_update_count={webhook_info.pending_update_count}, has_custom_certificate={webhook_info.has_custom_certificate}")
            if webhook_info.url:
                logger.warning(f"⚠️ 检测到 Bot 已设置 webhook: {webhook_info.url}，这将阻止 polling 工作！")
                logger.info("正在删除 webhook...")
                result = bot.delete_webhook(drop_pending_updates=True)
                logger.info(f"Webhook 删除结果: {result}")
                # 再次检查确认
                webhook_info_after = bot.get_webhook_info()
                if webhook_info_after.url:
                    logger.error(f"❌ Webhook 删除失败！仍然存在: {webhook_info_after.url}")
                else:
                    logger.info("✅ Webhook 已成功删除，现在可以正常使用 polling")
            else:
                logger.info("✅ Bot 未设置 webhook，可以使用 polling")
        except Exception as webhook_error:
            logger.error(f"❌ 检查 webhook 时出错: {webhook_error}", exc_info=True)
        
        logger.info("开始轮询 Telegram 更新...")
        logger.info("如果收到消息但没有日志，可能是轮询没有正常运行")
        
        # 跳过测试获取更新（可能会阻塞），直接开始轮询
        logger.info("跳过测试获取更新，直接开始轮询...")
        
        # 再次检查消息处理器
        try:
            handlers_count = len(bot.message_handlers) if hasattr(bot, 'message_handlers') else 0
            logger.info(f"轮询开始前，再次检查消息处理器数量: {handlers_count}")
            if hasattr(bot, 'message_handlers'):
                for i, handler in enumerate(bot.message_handlers):
                    logger.info(f"  处理器 {i+1}: {handler}")
        except Exception as e:
            logger.warning(f"检查消息处理器详情时出错: {e}")
        
        # 添加异常处理，确保能看到轮询过程中的错误
        try:
            logger.info("开始 infinity_polling...")
            logger.info("⚠️ 重要：如果发送消息后没有日志，请检查：")
            logger.info("   1. Webhook 是否已删除（应该看到 'Webhook 已成功删除'）")
            logger.info("   2. 消息处理器数量是否大于 0")
            logger.info("   3. 网络连接是否正常")
            
            # 使用手动轮询方式（更可靠）
            logger.info("📡 开始使用手动轮询方式监听 Telegram 消息...")
            logger.info("💡 提示：现在可以向 Bot 发送 /id 命令测试")
            
            last_update_id = None
            poll_count = 0
            
            # 强制删除 webhook 并重置 offset（确保能获取新消息）
            try:
                logger.info("🔄 强制删除 webhook 并重置 offset...")
                bot.delete_webhook(drop_pending_updates=True)
                # 获取一次更新以确认连接正常，但不处理（用于重置 offset）
                # 使用 offset=None 或不传 offset 来获取所有待处理的更新
                test_updates = bot.get_updates(timeout=1)
                if test_updates:
                    # 如果有待处理的更新，更新 offset 到最新（跳过这些旧更新）
                    last_update_id = test_updates[-1].update_id + 1
                    logger.info(f"✅ 重置 offset 到: {last_update_id}，跳过了 {len(test_updates)} 个待处理更新")
                    logger.info(f"💡 提示：这些旧更新将被跳过，只处理新消息")
                else:
                    last_update_id = None
                    logger.info("✅ 没有待处理的更新，将从最新消息开始接收")
            except Exception as reset_error:
                logger.warning(f"⚠️ 重置 offset 时出错（可忽略）: {reset_error}")
                last_update_id = None
            
            # 网络错误重试计数和退避时间
            network_error_count = 0
            max_network_errors = 10  # 连续网络错误的最大次数
            base_retry_delay = 5  # 基础重试延迟（秒）
            max_retry_delay = 60  # 最大重试延迟（秒）
            
            while True:
                try:
                    poll_count += 1
                    if poll_count % 100 == 0:  # 每100次轮询记录一次
                        logger.info(f"⏰ 轮询仍在运行中... (已轮询 {poll_count} 次, offset={last_update_id})")
                    
                    # 获取更新（如果 last_update_id 为 None，不传 offset 参数）
                    try:
                        if last_update_id is not None:
                            updates = bot.get_updates(timeout=20, offset=last_update_id, long_polling_timeout=20)
                        else:
                            updates = bot.get_updates(timeout=20, long_polling_timeout=20)
                        
                        # 成功获取更新，重置网络错误计数
                        if network_error_count > 0:
                            logger.info(f"✅ 网络连接已恢复（之前连续失败 {network_error_count} 次）")
                            network_error_count = 0
                            
                    except Exception as get_updates_error:
                        error_msg = str(get_updates_error)
                        error_type = type(get_updates_error).__name__
                        
                        # 检查是否是 409 冲突错误（多个 bot 实例同时运行）
                        is_conflict_error = False
                        error_code = None
                        
                        # 尝试获取错误代码（telebot 的 ApiTelegramException 可能有 error_code 属性）
                        if hasattr(get_updates_error, 'error_code'):
                            error_code = get_updates_error.error_code
                            if error_code == 409:
                                is_conflict_error = True
                        elif hasattr(get_updates_error, 'result') and hasattr(get_updates_error.result, 'error_code'):
                            error_code = get_updates_error.result.error_code
                            if error_code == 409:
                                is_conflict_error = True
                        # 也可以通过错误消息判断
                        elif '409' in error_msg or 'Conflict' in error_msg or 'terminated by other getUpdates' in error_msg:
                            is_conflict_error = True
                            error_code = 409
                        
                        if is_conflict_error:
                            # 409 冲突错误：有多个 bot 实例在运行
                            logger.error(f"❌ Telegram Bot 冲突错误 (409): 检测到多个 bot 实例同时运行")
                            logger.error(f"   错误信息: {error_msg[:300]}")
                            logger.error(f"   💡 解决方案:")
                            logger.error(f"      1. 检查是否有多个进程/线程在运行 bot")
                            logger.error(f"      2. 检查是否有其他服务/脚本也在使用同一个 bot token")
                            logger.error(f"      3. 停止其他 bot 实例后，当前实例将在 30 秒后自动重试")
                            logger.error(f"      4. 如果问题持续，请检查:")
                            logger.error(f"         - 是否有多个 worker 进程（Gunicorn/Uvicorn）")
                            logger.error(f"         - 是否有定时任务也在启动 bot")
                            logger.error(f"         - 是否有其他服务器也在运行相同的 bot")
                            
                            # 等待较长时间后重试（给其他实例时间停止）
                            retry_delay = 30
                            logger.info(f"   将在 {retry_delay} 秒后重试...")
                            time.sleep(retry_delay)
                            continue
                        
                        # 判断是否是网络连接错误
                        is_network_error = any(keyword in error_msg.lower() for keyword in [
                            'network is unreachable',
                            'connection refused',
                            'connection timeout',
                            'connection error',
                            'name resolution failed',
                            'failed to establish',
                            'max retries exceeded',
                            'connection aborted',
                            'dns',
                            'timeout'
                        ]) or 'ConnectionError' in error_type or 'Timeout' in error_type
                        
                        if is_network_error:
                            network_error_count += 1
                            
                            # 计算指数退避延迟时间
                            retry_delay = min(base_retry_delay * (2 ** min(network_error_count - 1, 4)), max_retry_delay)
                            
                            if network_error_count == 1:
                                logger.warning(f"⚠️ 网络连接错误（第 {network_error_count} 次）: {error_type}")
                                logger.warning(f"   错误信息: {error_msg[:200]}")
                                logger.warning(f"   将在 {retry_delay} 秒后重试...")
                            elif network_error_count <= 5:
                                logger.warning(f"⚠️ 网络连接错误（连续第 {network_error_count} 次）: {error_type}")
                                logger.warning(f"   将在 {retry_delay} 秒后重试...")
                            elif network_error_count <= max_network_errors:
                                logger.error(f"❌ 网络连接持续失败（连续第 {network_error_count} 次）: {error_type}")
                                logger.error(f"   错误信息: {error_msg[:200]}")
                                logger.error(f"   将在 {retry_delay} 秒后重试...")
                                logger.error(f"   💡 提示：请检查服务器网络连接、防火墙设置和 DNS 配置")
                            else:
                                logger.error(f"❌ 网络连接严重失败（连续第 {network_error_count} 次，超过最大次数 {max_network_errors}）")
                                logger.error(f"   错误类型: {error_type}")
                                logger.error(f"   错误信息: {error_msg[:200]}")
                                logger.error(f"   将在 {retry_delay} 秒后继续重试...")
                                logger.error(f"   💡 建议：")
                                logger.error(f"      1. 检查服务器网络连接状态")
                                logger.error(f"      2. 检查防火墙是否阻止了 api.telegram.org")
                                logger.error(f"      3. 检查 DNS 解析是否正常（尝试: ping api.telegram.org）")
                                logger.error(f"      4. 检查是否需要配置代理")
                                network_error_count = 0  # 重置计数，避免日志过多
                        else:
                            # 非网络错误，使用较短的延迟
                            logger.error(f"❌ 获取更新时出错（非网络错误）: {error_type}")
                            logger.error(f"   错误信息: {error_msg[:200]}")
                            retry_delay = 2
                            network_error_count = 0  # 重置网络错误计数
                        
                        time.sleep(retry_delay)
                        continue
                    
                    if updates:
                        # 只在开发环境或需要调试时记录详细更新信息
                        if not settings.is_production:
                            logger.debug(f"✅ 收到 {len(updates)} 个更新")
                            # 记录更新内容（用于调试）
                            for update in updates:
                                if hasattr(update, 'message') and update.message:
                                    msg = update.message
                                    text = getattr(msg, 'text', '') or ''
                                    chat_id = getattr(msg.chat, 'id', '未知') if hasattr(msg, 'chat') else '未知'
                                    chat_type = getattr(msg.chat, 'type', '未知') if hasattr(msg, 'chat') else '未知'
                                    logger.debug(f"📨 更新内容: update_id={update.update_id}, message_id={getattr(msg, 'message_id', '未知')}, text='{text[:50]}', chat_id={chat_id}, chat_type={chat_type}")
                    
                    # 处理更新
                    for update in updates:
                        try:
                            # 调用 bot 的内部处理器（不需要手动调用，因为使用了装饰器）
                            # 这里只是为了记录日志
                            logger.debug(f"处理更新: {update.update_id}")
                        except Exception as process_error:
                            logger.error(f"处理更新时出错: {process_error}", exc_info=True)
                        
                        # 更新 offset 到最新
                        if update.update_id > (last_update_id or 0):
                            last_update_id = update.update_id + 1
                
                except Exception as polling_error:
                    logger.error(f"轮询过程中出错: {polling_error}", exc_info=True)
                    # 短暂延迟后继续
                    time.sleep(2)
                    continue
        
        except Exception as e:
            logger.error(f"轮询启动失败: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Bot 运行失败: {e}", exc_info=True)