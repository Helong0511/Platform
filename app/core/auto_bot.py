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
        """处理 /stats 或 /conversion 命令：显示转化统计信息"""
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
        
        # 发送处理中消息
        processing_message = bot.send_message(chat_id, "正在统计转化数据，请稍候...")
        
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
                        chat_id=chat_id,
                        message_id=processing_message.message_id,
                        text=stats_message
                    )
                    
            except Exception as e:
                logger.error(f"处理转化统计时发生错误: {e}", exc_info=True)
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=processing_message.message_id,
                        text="统计失败，请稍后重试\n\n错误信息: " + str(e)[:100]
                    )
                except:
                    pass
        
        # 启动线程处理统计
        thread = threading.Thread(target=process_stats, daemon=True)
        thread.start()
    
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
                                elif hasattr(update, 'callback_query') and update.callback_query:
                                    callback = update.callback_query
                                    data = getattr(callback, 'data', '') or ''
                                    chat_id = getattr(callback.message.chat, 'id', '未知') if hasattr(callback, 'message') and callback.message else '未知'
                                    chat_type = getattr(callback.message.chat, 'type', '未知') if hasattr(callback, 'message') and callback.message and hasattr(callback.message, 'chat') else '未知'
                                    logger.debug(f"📨 回调查询: update_id={update.update_id}, callback_data='{data}', chat_id={chat_id}, chat_type={chat_type}")
                        else:
                            # 生产环境只记录简要信息
                            logger.debug(f"收到 {len(updates)} 个更新")
                        
                        # 处理更新（不记录日志，避免重复）
                        try:
                            # 确保更新被正确处理
                            for update in updates:
                                # 处理更新（详细日志已在上面记录，这里不再重复）
                                if hasattr(update, 'message') and update.message:
                                    msg = update.message
                            
                            # 检查消息处理器
                            handlers_count = len(bot.message_handlers) if hasattr(bot, 'message_handlers') else 0
                            logger.info(f"🔍 处理前，消息处理器数量: {handlers_count}")
                            
                            # 优先使用手动调用处理器（更可靠，特别是对于命令）
                            # 先手动处理命令和回调，确保能正确响应
                            logger.info("🔄 开始手动处理更新（优先处理命令和回调）...")
                            
                            # 处理回调查询（优先级最高）
                            for update in updates:
                                if hasattr(update, 'callback_query') and update.callback_query:
                                    callback = update.callback_query
                                    data = getattr(callback, 'data', '') or ''
                                    logger.info(f"🔍 检测到回调查询: callback_data='{data}'，尝试手动调用处理器...")
                                    try:
                                        handler_found = False
                                        if hasattr(bot, 'callback_query_handlers') and bot.callback_query_handlers:
                                            for handler in bot.callback_query_handlers:
                                                handler_func = handler.get('function')
                                                if handler_func:
                                                    logger.info(f"✅ 找到回调查询处理器: {handler_func.__name__}")
                                                    handler_func(callback)
                                                    logger.info(f"✅ 手动调用 {handler_func.__name__} 完成")
                                                    handler_found = True
                                                    break
                                        
                                        if not handler_found:
                                            logger.warning(f"⚠️ 未找到回调查询处理器")
                                    except Exception as callback_error:
                                        logger.error(f"❌ 手动调用回调查询处理器出错: {callback_error}", exc_info=True)
                            
                            # 处理命令消息（优先级高）
                            for update in updates:
                                if hasattr(update, 'message') and update.message:
                                    msg = update.message
                                    text = getattr(msg, 'text', '') or ''
                                    chat_type = msg.chat.type if hasattr(msg, 'chat') and hasattr(msg.chat, 'type') else '未知'
                                    
                                    # 检查是否是群组消息，以及是否包含 Bot 的提及
                                    is_group = chat_type in ['group', 'supergroup']
                                    bot_mentioned = False
                                    bot_username = None
                                    
                                    # 获取 Bot 的用户名
                                    try:
                                        bot_info = bot.get_me()
                                        bot_username = bot_info.username if bot_info else None
                                    except:
                                        pass
                                    
                                    # 检查消息中是否包含 Bot 的提及（群组中需要）
                                    if is_group and bot_username:
                                        # 检查消息文本中是否包含 @botname
                                        if f'@{bot_username}' in text:
                                            bot_mentioned = True
                                        # 检查消息 entities 中是否有 mention
                                        if hasattr(msg, 'entities') and msg.entities:
                                            for entity in msg.entities:
                                                if entity.type == 'mention':
                                                    mention_text = text[entity.offset:entity.offset + entity.length]
                                                    if mention_text == f'@{bot_username}':
                                                        bot_mentioned = True
                                                        break
                                    
                                    # 如果是命令，优先手动处理
                                    if text and text.startswith('/'):
                                        command = text.split()[0] if text else ''  # 获取命令部分（如 '/id' 或 '/id@botname'）
                                        # 移除 @botname 部分（如果有）
                                        if '@' in command:
                                            command = command.split('@')[0]
                                        
                                        # 在群组中，检查是否需要 @botname（Telegram 隐私模式）
                                        if is_group:
                                            logger.info(f"🔍 检测到群组命令: {command} (chat_type={chat_type}, bot_mentioned={bot_mentioned}, bot_username=@{bot_username})")
                                            # 如果群组中命令没有 @botname，记录警告但继续处理（某些情况下仍可工作）
                                            if not bot_mentioned and bot_username:
                                                logger.warning(f"⚠️ 群组中的命令 {command} 没有 @{bot_username}，可能无法响应（Telegram 隐私模式）")
                                                logger.info(f"💡 提示：在群组中使用命令时，请使用 /{command.split('/')[-1]}@{bot_username} 格式，或直接 @{bot_username} 后发送命令")
                                        else:
                                            logger.info(f"🔍 检测到私聊命令: {command} (chat_type={chat_type})")
                                        
                                        try:
                                            handler_found = False
                                            for handler in bot.message_handlers:
                                                handler_func = handler.get('function')
                                                filters = handler.get('filters', {})
                                                commands = filters.get('commands', [])
                                                
                                                # 检查是否是匹配的命令处理器
                                                # 支持 '/id' 匹配 commands=['id']
                                                command_match = False
                                                for cmd in commands:
                                                    if command == f'/{cmd}' or command == cmd:
                                                        command_match = True
                                                        break
                                                
                                                if command_match:
                                                    logger.info(f"✅ 找到匹配的命令处理器: {handler_func.__name__} (命令: {commands}, 匹配: {command})")
                                                    try:
                                                        handler_func(msg)
                                                        logger.info(f"✅ 手动调用 {handler_func.__name__} 完成，命令: {command}")
                                                        handler_found = True
                                                        break
                                                    except Exception as handler_error:
                                                        logger.error(f"❌ 调用命令处理器 {handler_func.__name__} 时出错: {handler_error}", exc_info=True)
                                                        logger.error(f"❌ 错误堆栈: {traceback.format_exc()}")
                                            
                                            if not handler_found:
                                                logger.warning(f"⚠️ 未找到命令 {command} 的处理器，尝试使用 process_new_updates")
                                        except Exception as manual_call_error:
                                            logger.error(f"❌ 手动调用命令处理器出错: {manual_call_error}", exc_info=True)
                            
                            # 使用 process_new_updates 处理其他消息（标准方式，作为备用）
                            logger.info("🔄 调用 bot.process_new_updates() 处理其他消息...")
                            try:
                                bot.process_new_updates(updates)
                                logger.info("✅ bot.process_new_updates() 调用完成")
                            except Exception as process_error:
                                logger.error(f"❌ process_new_updates 出错: {process_error}", exc_info=True)
                                logger.error(f"❌ 错误堆栈: {traceback.format_exc()}")
                            
                            # 如果 process_new_updates 没有触发处理器，尝试手动调用（备用方案）
                            # 检查是否有消息或回调查询需要处理
                            for update in updates:
                                # 处理其他非命令消息（如果 process_new_updates 没有处理）
                                if hasattr(update, 'message') and update.message:
                                    msg = update.message
                                    text = getattr(msg, 'text', '') or ''
                                    # 只处理非命令消息（命令已在上面处理）
                                    if text and not text.startswith('/'):
                                        logger.info(f"🔍 检查非命令消息是否需要手动处理: text='{text[:30]}'")
                                        # 这里可以添加其他消息类型的处理逻辑
                            
                            # 检查是否有异常被静默吞掉
                            logger.info("✅ 更新处理完成")
                        except Exception as process_error:
                            logger.error(f"❌ 处理更新时出错: {process_error}", exc_info=True)
                            logger.error(f"❌ 错误堆栈: {traceback.format_exc()}")
                        # 更新 offset
                        last_update_id = updates[-1].update_id + 1
                        logger.info(f"✅ 已处理更新，新的 offset: {last_update_id}")
                    else:
                        # 没有更新是正常的，继续轮询
                        pass
                        
                except KeyboardInterrupt:
                    logger.info("收到键盘中断信号，停止轮询")
                    raise
                except Exception as poll_error:
                    logger.error(f"❌ 轮询错误: {poll_error}", exc_info=True)
                    time.sleep(1)  # 出错后等待1秒再继续
            logger.info("infinity_polling 已退出（这不应该发生）")
        except KeyboardInterrupt:
            logger.info("收到键盘中断信号")
            raise
        except Exception as polling_error:
            logger.error(f"轮询过程中发生错误: {polling_error}", exc_info=True)
            logger.error(f"错误类型: {type(polling_error).__name__}")
            raise
    except KeyboardInterrupt:
        logger.info("收到终止信号，正在优雅关闭机器人...")
    except telebot.apihelper.ApiException as api_error:
        error_msg = str(api_error)
        error_code = getattr(api_error, 'error_code', None) or getattr(api_error, 'result', {}).get('error_code', None) if hasattr(api_error, 'result') else None
        
        # 检查是否是 409 冲突错误
        if error_code == 409 or '409' in error_msg or 'Conflict' in error_msg or 'terminated by other getUpdates' in error_msg:
            logger.error(f"❌ Telegram Bot 冲突错误 (409): 检测到多个 bot 实例同时运行")
            logger.error(f"   API 错误详情: {type(api_error).__name__}: {error_msg[:300]}")
            logger.error(f"   💡 解决方案:")
            logger.error(f"      1. 检查是否有多个进程/线程在运行 bot")
            logger.error(f"      2. 检查是否有其他服务/脚本也在使用同一个 bot token")
            logger.error(f"      3. 停止其他 bot 实例后重启当前服务")
            logger.error(f"      4. 如果问题持续，请检查:")
            logger.error(f"         - 是否有多个 worker 进程（Gunicorn/Uvicorn）")
            logger.error(f"         - 是否有定时任务也在启动 bot")
            logger.error(f"         - 是否有其他服务器也在运行相同的 bot")
        else:
            logger.error(f"Telegram API 错误: {api_error}", exc_info=True)
            logger.error(f"API 错误详情: {type(api_error).__name__}: {error_msg}")
    except Exception as e:
        error_msg = str(e)
        # 检查是否是 409 冲突错误（可能被包装在其他异常中）
        if '409' in error_msg or 'Conflict' in error_msg or 'terminated by other getUpdates' in error_msg:
            logger.error(f"❌ Telegram Bot 冲突错误 (409): 检测到多个 bot 实例同时运行")
            logger.error(f"   错误信息: {error_msg[:300]}")
            logger.error(f"   💡 解决方案:")
            logger.error(f"      1. 检查是否有多个进程/线程在运行 bot")
            logger.error(f"      2. 检查是否有其他服务/脚本也在使用同一个 bot token")
            logger.error(f"      3. 停止其他 bot 实例后重启当前服务")
        else:
            logger.error(f"机器人运行时发生错误: {e}", exc_info=True)
            logger.error(f"错误类型: {type(e).__name__}")
    finally:
        logger.info("机器人已停止运行")


def _acquire_bot_lock():
    """
    尝试获取 Bot 启动锁（文件锁）
    在多进程环境下，确保只有一个进程启动 Bot
    
    Returns:
        bool: 是否成功获取锁
    """
    global _bot_lock_file, _bot_lock_acquired

    if _bot_lock_acquired:
        return True

    # os 模块已在文件顶部导入，直接使用
    current_pid = os.getpid()

    try:
        # 创建锁文件路径（在项目根目录的 logs 目录下）
        lock_file_path = Path(__file__).parent.parent.parent / "logs" / "telegram_bot.lock"
        lock_file_path.parent.mkdir(parents=True, exist_ok=True)

        # 跨平台文件锁
        if HAS_FCNTL:
            # Unix/Linux: 使用 fcntl（文本模式）
            _bot_lock_file = open(lock_file_path, 'w')
            try:
                fcntl.flock(_bot_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                _bot_lock_acquired = True
            except (IOError, OSError) as e:
                # 无法获取锁（其他进程已持有）
                _close_lock_file()
                logger.info(f"[PID:{current_pid}] 无法获取 Telegram Bot 启动锁（其他进程可能已启动）: {e}")
                return False
        elif HAS_MSVCRT:
            # Windows: 使用 msvcrt（需要二进制模式）
            _bot_lock_file = open(lock_file_path, 'wb+')
            try:
                # 锁定文件的第一个字节
                msvcrt.locking(_bot_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                _bot_lock_acquired = True
                # 写入当前进程信息（需要转换为字节）
                _bot_lock_file.write(f"PID: {current_pid}\n".encode('utf-8'))
                _bot_lock_file.flush()
                logger.info(f"[PID:{current_pid}] 成功获取 Telegram Bot 启动锁")
                return True
            except IOError as e:
                # 无法获取锁（其他进程已持有）
                _close_lock_file()
                logger.info(f"[PID:{current_pid}] 无法获取 Telegram Bot 启动锁（其他进程可能已启动）: {e}")
                return False
        else:
            # 没有文件锁支持，使用简单的文件存在性检查（不完美但可用）
            if lock_file_path.exists():
                # 检查锁文件中的 PID 是否还在运行
                try:
                    with open(lock_file_path, 'r') as f:
                        pid_line = f.readline()
                        if pid_line.startswith("PID: "):
                            old_pid = int(pid_line.split(": ")[1].strip())
                            # 检查进程是否还在运行
                            try:
                                os.kill(old_pid, 0)  # 发送信号 0 检查进程是否存在
                                # 进程还在运行
                                logger.info(f"[PID:{current_pid}] 无法获取 Telegram Bot 启动锁（进程 {old_pid} 正在运行）")
                                return False
                            except (OSError, ProcessLookupError):
                                # 进程不存在，可以获取锁
                                pass
                except Exception:
                    pass
            
            # 可以获取锁
            _bot_lock_file = open(lock_file_path, 'w')
            _bot_lock_acquired = True

        # 写入当前进程信息（非 Windows 路径）
        if not HAS_MSVCRT:
            _bot_lock_file.write(f"PID: {current_pid}\n")
            _bot_lock_file.flush()

        logger.info(f"[PID:{current_pid}] 成功获取 Telegram Bot 启动锁")
        return True
    except Exception as e:
        logger.warning(f"[PID:{current_pid}] 获取 Telegram Bot 启动锁时发生错误: {e}")
        _close_lock_file()
        return False


def _close_lock_file():
    """安全关闭锁文件"""
    global _bot_lock_file
    if _bot_lock_file:
        try:
            _bot_lock_file.close()
        except Exception:
            pass
        finally:
            _bot_lock_file = None


def _release_bot_lock():
    """释放 Bot 启动锁"""
    global _bot_lock_file, _bot_lock_acquired

    if _bot_lock_file and _bot_lock_acquired:
        current_pid = os.getpid()
        lock_file_path = None
        try:
            # 获取锁文件路径
            lock_file_path = Path(__file__).parent.parent.parent / "logs" / "telegram_bot.lock"
            
            # 跨平台释放锁
            if HAS_FCNTL:
                # Unix/Linux: 使用 fcntl
                fcntl.flock(_bot_lock_file.fileno(), fcntl.LOCK_UN)
            elif HAS_MSVCRT:
                # Windows: 使用 msvcrt
                msvcrt.locking(_bot_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            # 如果没有文件锁支持，直接关闭文件即可
            
            _bot_lock_file.close()
            
            # 删除锁文件（如果存在）
            if lock_file_path and lock_file_path.exists():
                try:
                    lock_file_path.unlink()
                except Exception:
                    pass
            
            logger.info(f"[PID:{current_pid}] 已释放 Telegram Bot 启动锁")
        except Exception as e:
            logger.warning(f"[PID:{current_pid}] 释放 Telegram Bot 启动锁时发生错误: {e}")
            # 确保文件被关闭
            try:
                if _bot_lock_file:
                    _bot_lock_file.close()
            except Exception:
                pass
            # 尝试删除锁文件
            if lock_file_path and lock_file_path.exists():
                try:
                    lock_file_path.unlink()
                except Exception:
                    pass
        finally:
            _bot_lock_file = None
            _bot_lock_acquired = False


def start_bot():
    """启动 Telegram Bot 轮询线程（仅在获取到锁的进程中启动）"""
    current_pid = os.getpid()
    logger.info(f"[PID:{current_pid}] 开始启动 Telegram Bot...")
    
    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    if not telegram_enabled:
        logger.info(f"[PID:{current_pid}] Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false），跳过启动")
        return False

    if not TELEBOT_AVAILABLE:
        logger.error(f"[PID:{current_pid}] pyTelegramBotAPI 未安装，无法启动 Bot")
        return False

    if not bot_initialized:
        logger.error(f"[PID:{current_pid}] Bot 未初始化，无法启动")
        return False

    if not bot:
        logger.error(f"[PID:{current_pid}] Bot 对象不存在，无法启动")
        return False

    # 尝试获取锁（多进程环境下，只有一个进程能获取到）
    if not _acquire_bot_lock():
        logger.info(f"[PID:{current_pid}] 其他进程已启动 Telegram Bot，跳过启动")
        return False

    try:
        logger.info(f"[PID:{current_pid}] 正在设置 Telegram Bot 命令...")
        # 设置 Bot 命令
        commands_list = [
            ("id", "查询聊天ID（群组中需使用 /id@botname）"),
            ("test", "测试内联按钮（群组中需使用 /test@botname）"),
            ("clock", "打卡（群组中需使用 /clock@botname）")
        ]

        com_set = []
        for com, desc in commands_list:
            try:
                com_set.append(BotCommand(command=com, description=desc))
            except Exception as er:
                logger.warning(f"添加命令 {com} 时发生错误: {er}")

        if com_set:
            try:
                bot.set_my_commands(commands=com_set)
                logger.info(f"[PID:{current_pid}] Telegram Bot 命令设置成功")
                
                # 获取 Bot 用户名，用于提示
                try:
                    bot_info = bot.get_me()
                    bot_username = bot_info.username if bot_info else None
                    if bot_username:
                        logger.info(f"[PID:{current_pid}] 💡 提示：在群组中使用命令时，请使用 /命令@{bot_username} 格式，或直接 @{bot_username} 后发送命令")
                        logger.info(f"[PID:{current_pid}] 💡 例如：/id@{bot_username} 或 @{bot_username} /id")
                except:
                    pass
            except Exception as e:
                logger.warning(f"[PID:{current_pid}] 设置 Telegram Bot 命令时发生错误: {e}")

        # 启动轮询线程（守护线程，主进程退出时自动退出）
        logger.info(f"[PID:{current_pid}] 正在启动 Telegram Bot 轮询线程...")
        bot_thread = threading.Thread(target=run_bot, daemon=True, name="TelegramBot")
        bot_thread.start()
        
        # 等待一小段时间，检查线程是否正常启动
        time.sleep(0.5)
        if bot_thread.is_alive():
            logger.info(f"[PID:{current_pid}] Telegram Bot 轮询线程已启动（线程ID: {bot_thread.ident}, 已获取锁）")
        else:
            logger.warning(f"[PID:{current_pid}] Telegram Bot 轮询线程启动后立即退出，可能存在问题")
        
        return True
    except Exception as e:
        logger.error(f"[PID:{current_pid}] 启动 Telegram Bot 时发生错误: {e}", exc_info=True)
        _release_bot_lock()
        return False


def has_bot_lock():
    """检查当前进程是否持有 Bot 启动锁"""
    return _bot_lock_acquired


def stop_bot():
    """停止 Telegram Bot 轮询（仅在持有锁的进程中停止）"""
    # 只有持有锁的进程才需要停止 Bot
    if _bot_lock_acquired and TELEBOT_AVAILABLE and bot_initialized and bot:
        current_pid = os.getpid()
        try:
            bot.stop_polling()
            logger.info(f"[PID:{current_pid}] Telegram Bot 轮询已停止")
        except Exception as e:
            logger.error(f"停止 Telegram Bot 时发生错误: {e}", exc_info=True)
        finally:
            _release_bot_lock()


# 命令处理器已在模块级别注册（见第 91-158 行）


async def send_telegram_message_with_buttons(
    message: str,
    chat_id: str | None = None,
    buttons: list[list[dict]] | None = None
) -> tuple[bool, int | None]:
    """
    发送带按钮的 Telegram 消息
    
    Args:
        message: 要发送的消息内容
        chat_id: 目标聊天ID（可选，默认使用配置中的 TELEGRAM_ADMIN）
        buttons: 按钮列表，格式：[[{"text": "按钮1", "callback_data": "data1"}, {"text": "按钮2", "callback_data": "data2"}], [{"text": "按钮3", "callback_data": "data3"}]]
                每个内层列表代表一行按钮
    
    Returns:
        tuple[bool, int | None]: (是否发送成功, 消息ID)
    """
    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    if not telegram_enabled:
        logger.debug("Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false），跳过发送消息")
        return False, None

    if not TELEBOT_AVAILABLE:
        logger.error("pyTelegramBotAPI 未安装，无法发送消息。请运行: pip install pyTelegramBotAPI")
        return False, None

    if not bot_initialized:
        logger.error("Telegram机器人未初始化，无法发送消息")
        return False, None

    if not bot:
        logger.error("Telegram机器人未初始化，无法发送消息")
        return False, None

    try:
        # 如果没有指定 chat_id，使用配置中的 TELEGRAM_ADMIN
        if chat_id is None:
            chat_id = getattr(settings, 'TELEGRAM_ADMIN', None) or None

        if not chat_id or not isinstance(chat_id, str) or not chat_id.strip():
            logger.error("发送Telegram消息失败: 无法获得收信息的用户或群组ID（请设置 TELEGRAM_ADMIN 环境变量）")
            return False, None

        # 检查消息长度（Telegram 最大 4096 字符）
        if len(message) > MAX_TELEGRAM_MESSAGE_LENGTH:
            message = truncate_message(message)

        # 创建内联键盘
        markup = None
        if buttons:
            markup = InlineKeyboardMarkup()
            for row in buttons:
                row_buttons = []
                for btn in row:
                    row_buttons.append(InlineKeyboardButton(text=btn.get("text", ""), callback_data=btn.get("callback_data", "")))
                markup.row(*row_buttons)

        # pyTelegramBotAPI 的 send_message 是同步的，需要在线程中执行
        loop = asyncio.get_event_loop()
        
        def _send():
            try:
                sent_message = bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
                return True, sent_message.message_id if sent_message else None
            except Exception as e:
                logger.error(f"发送Telegram消息失败: {e}", exc_info=True)
                return False, None

        try:
            success, message_id = await asyncio.wait_for(
                loop.run_in_executor(None, _send),
                timeout=8.0
            )
            if success:
                logger.debug(f"Telegram消息发送成功，消息ID: {message_id}")
            return success, message_id
        except asyncio.TimeoutError:
            logger.error("发送Telegram消息超时（超过8秒）")
            return False, None
    except Exception as e:
        logger.error(f"发送Telegram消息时发生错误: {e}", exc_info=True)
        return False, None


async def send_telegram_message(message: str, chat_id: str | None = None):
    """
    发送 Telegram 消息
    
    Args:
        message: 要发送的消息内容
        chat_id: 目标聊天ID（可选，默认使用配置中的 TELEGRAM_ADMIN）
    
    Returns:
        bool: 发送是否成功
    """
    # 检查是否启用 Telegram
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    if not telegram_enabled:
        logger.debug("Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false），跳过发送消息")
        return False

    if not TELEBOT_AVAILABLE:
        logger.error("pyTelegramBotAPI 未安装，无法发送消息。请运行: pip install pyTelegramBotAPI")
        return False

    if not bot_initialized:
        logger.error("Telegram机器人未初始化，无法发送消息")
        return False

    if not bot:
        logger.error("Telegram机器人未初始化，无法发送消息")
        return False

    try:
        # 如果没有指定 chat_id，使用配置中的 TELEGRAM_ADMIN
        if chat_id is None:
            chat_id = getattr(settings, 'TELEGRAM_ADMIN', None) or None

        if not chat_id or not isinstance(chat_id, str) or not chat_id.strip():
            logger.error("发送Telegram消息失败: 无法获得收信息的用户或群组ID（请设置 TELEGRAM_ADMIN 环境变量）")
            return False

        # 检查消息长度（Telegram 最大 4096 字符）
        if len(message) > MAX_TELEGRAM_MESSAGE_LENGTH:
            message = truncate_message(message)

        # pyTelegramBotAPI 的 send_message 是同步的，需要在线程中执行
        # 使用 asyncio 来避免阻塞异步事件循环
        # 同时设置超时，避免网络问题导致长时间阻塞
        loop = asyncio.get_event_loop()
        
        # 使用 asyncio.wait_for 包装，设置 8 秒超时（比外层的 10 秒稍短）
        # 这样可以确保即使内部的 requests 库超时（默认 15 秒），也能及时返回
        try:
            await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: bot.send_message(chat_id=chat_id.strip(), text=message)
                ),
                timeout=8.0
            )
            logger.info(f"Telegram消息发送成功: {chat_id}")
            return True
        except asyncio.TimeoutError:
            logger.warning(f"发送Telegram消息超时（超过8秒）: chat_id={chat_id}")
            return False
    except Exception as e:
        # 检查是否是 telebot 的 API 异常
        if TELEBOT_AVAILABLE and 'telebot' in str(type(e).__module__):
            logger.error(f"发送Telegram消息失败（API错误）: {e}")
        else:
            logger.error(f"发送Telegram消息失败: {e}", exc_info=True)
        return False


def get_custom_title_safe(member) -> str | None:
    """
    安全获取自定义头衔
    返回: 头衔字符串（可能为空）或 None（如果不是管理员）
    """
    # 1. 检查管理员状态
    if getattr(member, 'status', None) != "administrator":
        return None

    # 2. 安全获取属性
    title = getattr(member, 'custom_title', None)

    # 3. 处理不同情况
    if title is None:
        # 属性不存在（旧版API）
        return None
    if isinstance(title, str):
        # 清理头衔
        return re.sub(r'[\n\r\t]', '', title).strip()

    return None


def format_title_display(title: str) -> str:
    """格式化头衔显示"""
    if title is None:
        return "管理员"
    if title == "":
        return "管理员"
    return title


# 处理成员变动
if bot_initialized and TELEBOT_AVAILABLE:
    @bot.chat_member_handler()
    def handle_member_changes(update: types.ChatMemberUpdated):
        try:
            old = update.old_chat_member
            new = update.new_chat_member
            chat = update.chat

            # 新成员加入
            if old.status in ["left", "kicked", None] and new.status == "member":
                # 排除机器人自己
                if new.user.is_bot:
                    logger.debug(f"检测到机器人加入，跳过欢迎: {new.user.first_name}")
                    return

                logger.info(f"检测到新成员加入: {new.user.first_name} 在群组 {chat.id}")

                welcome_msg = f"欢迎 {new.user.first_name} 加入群组！🎉"
                bot.send_message(chat.id, welcome_msg)


            # 成员离开
            elif old.status == "member" and new.status in ["left", "kicked"]:
                # 排除机器人自己
                if new.user.is_bot:
                    logger.debug(f"检测到机器人离开，跳过告别: {new.user.first_name}")
                    return

                logger.info(f"检测到成员离开: {new.user.first_name} 从群组 {chat.id}")

                farewell_msg = f"{new.user.first_name} 已离开群组。👋"
                bot.send_message(chat.id, farewell_msg)

            # 获取头衔
            old_title = get_custom_title_safe(old)
            new_title = get_custom_title_safe(new)

            # 状态变化：成为管理员
            if old.status != "administrator" and new.status == "administrator":
                display = format_title_display(new_title)
                msg = f"🎖️ {new.user.first_name} 成为{display}"
                bot.send_message(update.chat.id, msg)

            # 管理员权限变更
            elif old.status == "administrator" and new.status == "administrator":
                if old_title != new_title:
                    old_display = format_title_display(old_title)
                    new_display = format_title_display(new_title)

                    operator = update.from_user.first_name
                    msg = f"📛 {operator} 更新了头衔: {old_display} → {new_display}"
                    bot.send_message(update.chat.id, msg)

        except Exception as t_err:
            logger.error(f"处理管理员变更出错: {t_err}", exc_info=True)


def get_bot_status_info() -> dict:
    """
    获取 Bot 状态信息（用于诊断）
    
    Returns:
        dict: 包含 Bot 状态信息的字典
    """
    status_info = {
        "telegram_enabled": getattr(settings, 'TELEGRAM_ENABLE', True),
        "telebot_available": TELEBOT_AVAILABLE,
        "bot_initialized": bot_initialized,
        "bot_exists": bot is not None,
        "has_lock": _bot_lock_acquired,
        "token_configured": bool(
            getattr(settings, 'TELEGRAM_TOKEN', None) and 
            isinstance(getattr(settings, 'TELEGRAM_TOKEN', None), str) and
            getattr(settings, 'TELEGRAM_TOKEN', None).strip()
        ),
        "admin_configured": bool(
            getattr(settings, 'TELEGRAM_ADMIN', None) and
            isinstance(getattr(settings, 'TELEGRAM_ADMIN', None), str) and
            getattr(settings, 'TELEGRAM_ADMIN', None).strip()
        ),
    }
    
    # 尝试获取 Bot 信息
    if bot_initialized and bot:
        try:
            bot_info = bot.get_me()
            status_info["bot_username"] = bot_info.username
            status_info["bot_id"] = bot_info.id
            status_info["bot_first_name"] = bot_info.first_name
            status_info["connection_test"] = "成功"
        except Exception as e:
            status_info["connection_test"] = f"失败: {str(e)}"
            status_info["bot_username"] = None
            status_info["bot_id"] = None
    
    # 检查线程状态
    for thread in threading.enumerate():
        if thread.name == "TelegramBot":
            status_info["bot_thread_alive"] = thread.is_alive()
            status_info["bot_thread_id"] = thread.ident
            break
    else:
        status_info["bot_thread_alive"] = False
        status_info["bot_thread_id"] = None
    
    return status_info
