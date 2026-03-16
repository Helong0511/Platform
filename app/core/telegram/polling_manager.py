"""
Telegram Bot 轮询管理模块

负责启动和管理 Bot 的长轮询
"""
import os
import time
import logging
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE
from app.core.telegram.file_lock import acquire_bot_lock, release_bot_lock
from app.core.config import settings


def _check_bot_available() -> bool:
    """检查 Bot 是否可用"""
    return bot_initialized and TELEBOT_AVAILABLE and bot is not None


def set_bot_commands():
    """设置 Bot 命令列表"""
    if not _check_bot_available():
        logger.warning("Bot 未初始化，无法设置命令")
        return
    
    try:
        from telebot.types import BotCommand
        
        commands_list = [
            ("id", "查询聊天 ID（群组中需使用 /id@botname）"),
            ("test", "测试内联按钮（群组中需使用 /test@botname）"),
            ("clock", "打卡（群组中需使用 /clock@botname）"),
            ("stats", "查看转化统计（群组中需使用 /stats@botname）"),
            ("help", "显示帮助信息"),
            ("ping", "测试 Bot 是否在线"),
            ("status", "查看系统状态"),
            ("clear", "清空聊天记录（仅管理员）")
        ]
        
        com_set = []
        for com, desc in commands_list:
            try:
                com_set.append(BotCommand(command=com, description=desc))
                logger.info(f"添加命令 {com} 成功")
            except Exception as er:
                logger.warning(f"添加命令 {com} 时发生错误：{er}")
        
        if com_set:
            bot.set_my_commands(commands=com_set)
            logger.info("Telegram Bot 命令设置成功")
            
    except Exception as e:
        logger.error(f"设置 Bot 命令失败：{e}", exc_info=True)


def start_polling():
    """
    启动 Telegram Bot 轮询（仅在获取到锁的进程中启动）
    
    Returns:
        bool: 是否成功启动
    """
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
    
    # 多进程环境下，增加随机延迟避免锁竞争
    delay = random.uniform(0.1, 1.0)
    logger.info(f"[PID:{current_pid}] 等待 {delay:.2f} 秒后尝试获取锁，避免竞争...")
    time.sleep(delay)
    
    # 尝试获取锁
    logger.info(f"[PID:{current_pid}] 尝试获取 Telegram Bot 启动锁...")
    lock_acquired = acquire_bot_lock()
    
    if not lock_acquired:
        logger.info(f"[PID:{current_pid}] 其他进程已启动 Telegram Bot，或无法获取锁，跳过启动...")
        return False
    
    # 验证是否已有其他 Bot 实例在运行
    try:
        logger.info(f"[PID:{current_pid}] 验证是否已有其他 Bot 实例在运行...")
        bot_info = bot.get_me()
        logger.info(f"[PID:{current_pid}] 验证成功，Bot 可以正常运行：@{bot_info.username}")
        
        # 发送启动消息（只有真正获取到锁的进程才发送）
        try:
            from app.core.telegram.message_sender import send_telegram_message
            from app.core.config import settings
            from app.core.constants import TELEGRAM_BOT_START_DELAY
            import time
            time.sleep(TELEGRAM_BOT_START_DELAY)
            send_telegram_message("✅ Telegram 机器人已启动")
            logger.info(f"[PID:{current_pid}] 已发送 Telegram 机器人启动消息")
        except Exception as msg_err:
            logger.warning(f"[PID:{current_pid}] 发送启动消息失败：{msg_err}")
    except Exception as e:
        error_msg = str(e)
        if '409' in error_msg or 'Conflict' in error_msg or 'terminated by other getUpdates' in error_msg:
            logger.error(f"[PID:{current_pid}] 验证失败：检测到其他 Bot 实例正在运行")
            release_bot_lock()
            return False
        else:
            logger.warning(f"[PID:{current_pid}] 验证时发生错误，但继续启动：{e}")
    
    try:
        # 显式注册消息处理器和回调处理器（确保被正确注册）
        if bot_initialized and TELEBOT_AVAILABLE:
            try:
                # 直接注册消息处理器函数
                from app.core.telegram.command_handlers.id_command import get_chat_id
                from app.core.telegram.command_handlers.start_command import cmd_start
                from app.core.telegram.command_handlers.help_command import cmd_help
                from app.core.telegram.callback_handlers.menu_callbacks import handle_menu_callbacks
                from app.core.telegram.callback_handlers.postback_approval import handle_postback_approval
                
                # 调试函数：记录所有收到的消息（放在最后注册，避免拦截命令）
                def debug_all_messages(message):
                    logger.info(f"[DEBUG] 收到消息：text={message.text}, chat_id={message.chat.id}, from_user={message.from_user.id}")
                
                # 手动注册消息处理器（先注册特定命令）
                logger.info("正在注册 /start 命令处理器...")
                bot.message_handler(commands=['start'])(cmd_start)
                logger.info("正在注册 /help 命令处理器...")
                bot.message_handler(commands=['help'])(cmd_help)
                logger.info("正在注册 /id 命令处理器...")
                bot.message_handler(commands=['id'])(get_chat_id)
                
                # 手动注册回调处理器
                logger.info("正在注册回调处理器...")
                bot.callback_query_handler(func=lambda call: call.data in ["View", "clock"])(handle_menu_callbacks)
                bot.callback_query_handler(func=lambda call: call.data.startswith("postback_approve_") or call.data.startswith("postback_reject_"))(handle_postback_approval)
                
                # 最后注册通用调试处理器
                logger.info("正在注册通用调试消息处理器...")
                bot.message_handler(func=lambda message: True)(debug_all_messages)
                
                logger.info("消息处理器和回调处理器已成功注册")
            except Exception as import_err:
                logger.error(f"注册处理器时出错：{import_err}", exc_info=True)
        
        # 设置 Bot 命令
        set_bot_commands()
        
        # 检查消息处理器
        handlers_count = len(bot.message_handlers) if hasattr(bot, 'message_handlers') else 0
        logger.info(f"开始轮询前，Bot 消息处理器数量：{handlers_count}")
        
        if handlers_count == 0:
            logger.warning("警告：没有注册任何消息处理器！命令可能无法工作")
        
        # 检查并删除可能存在的 webhook
        try:
            logger.info("检查并删除可能存在的 webhook...")
            bot.delete_webhook()
            logger.info("Webhook 已删除（如果存在）")
        except Exception as e:
            logger.warning(f"删除 webhook 时出错：{e}")
        
        # 启动轮询
        logger.info("开始 Telegram Bot 长轮询...")
        logger.info("按 Ctrl+C 停止轮询")
        
        # 使用非阻塞方式启动轮询
        bot.polling(
            none_stop=True,
            interval=0,
            timeout=60,
            allowed_updates=['message', 'callback_query']
        )
        
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止轮询...")
    except Exception as e:
        logger.error(f"轮询过程中发生错误：{e}", exc_info=True)
    finally:
        # 释放锁
        release_bot_lock()
        logger.info("Telegram Bot 已停止")
    
    return True


def start_bot_thread():
    """
    在独立线程中启动 Bot 轮询
    
    Returns:
        bool: 线程是否成功启动（不代表一定获取到锁）
    """
    import threading
    
    # 先检查 Bot 是否可用
    if not _check_bot_available():
        logger.error("Bot 未初始化，无法启动轮询线程")
        return False
    
    # 定义线程运行函数
    def run_polling():
        logger.info("Telegram Bot 轮询线程开始运行")
        try:
            start_polling()
        except Exception as e:
            logger.error(f"Telegram Bot 轮询线程出错：{e}", exc_info=True)
        logger.info("Telegram Bot 轮询线程已结束")
    
    # 创建并启动线程
    thread = threading.Thread(target=run_polling, daemon=True, name="TelegramBot")
    thread.start()
    logger.info("Telegram Bot 轮询线程已启动")
    
    return True
