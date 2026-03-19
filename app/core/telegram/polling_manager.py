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
from app.core.telegram.shared_state import get_shared_state, update_shared_state, is_bot_running
from app.core.config import settings

# 标记处理器是否已注册
_handlers_registered = False

# 标记 Bot 是否已经启动
_bot_started = False


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
            ("start", "启动 Bot"),
            ("help", "显示帮助信息"),
            ("id", "查询聊天 ID（群组中需使用 /id@botname）")
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


def register_handlers():
    """注册消息处理器和回调处理器（仅注册一次）"""
    global _handlers_registered
    
    if _handlers_registered:
        logger.info("处理器已注册，跳过重复注册")
        return
    
    if not _check_bot_available():
        logger.warning("Bot 未初始化，无法注册处理器")
        return
    
    try:
        from app.core.telegram.command_handlers.id_command import get_chat_id
        from app.core.telegram.command_handlers.start_command import cmd_start
        from app.core.telegram.command_handlers.help_command import cmd_help
        from app.core.telegram.callback_handlers.menu_callbacks import handle_menu_callbacks
        from app.core.telegram.callback_handlers.postback_approval import handle_postback_approval
        
        def debug_all_messages(message):
            logger.info(f"[DEBUG] 收到消息：text={message.text}, chat_id={message.chat.id}, from_user={message.from_user.id}")
        
        logger.info("正在注册 /start 命令处理器...")
        bot.message_handler(commands=['start'])(cmd_start)
        logger.info("正在注册 /help 命令处理器...")
        bot.message_handler(commands=['help'])(cmd_help)
        logger.info("正在注册 /id 命令处理器...")
        bot.message_handler(commands=['id'])(get_chat_id)
        
        logger.info("正在注册回调处理器...")
        bot.callback_query_handler(func=lambda call: call.data in ["View", "clock"])(handle_menu_callbacks)
        bot.callback_query_handler(func=lambda call: call.data.startswith("postback_approve_") or call.data.startswith("postback_reject_"))(handle_postback_approval)
        
        logger.info("正在注册通用调试消息处理器...")
        bot.message_handler(func=lambda message: True)(debug_all_messages)
        
        _handlers_registered = True
        logger.info("消息处理器和回调处理器已成功注册")
        
    except Exception as import_err:
        logger.error(f"注册处理器时出错：{import_err}", exc_info=True)


def start_polling():
    """
    启动 Telegram Bot 轮询（仅在获取到锁的进程中启动）
    支持自动重连机制
    
    Returns:
        bool: 是否成功启动
    """
    global _bot_started
    
    current_pid = os.getpid()
    
    # 检查是否已经启动了 Bot
    if _bot_started:
        logger.info(f"[PID:{current_pid}] Telegram Bot 已经启动，跳过重复启动...")
        return False
    
    # 检查共享状态
    if is_bot_running():
        logger.info(f"[PID:{current_pid}] Telegram Bot 已在其他进程中运行，跳过启动...")
        return False
    
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
    delay = random.uniform(0.1, 2.0)
    logger.info(f"[PID:{current_pid}] 等待 {delay:.2f} 秒后尝试获取锁，避免竞争...")
    time.sleep(delay)
    
    # 尝试获取锁
    logger.info(f"[PID:{current_pid}] 尝试获取 Telegram Bot 启动锁...")
    lock_acquired = acquire_bot_lock()
    
    if not lock_acquired:
        logger.info(f"[PID:{current_pid}] 其他进程已启动 Telegram Bot，或无法获取锁，跳过启动...")
        return False
    
    # 再次检查共享状态，防止竞态条件
    if is_bot_running():
        logger.info(f"[PID:{current_pid}] Telegram Bot 已在其他进程中运行，跳过启动...")
        release_bot_lock()
        return False
    
    # 标记 Bot 已经启动
    _bot_started = True
    logger.info(f"[PID:{current_pid}] 成功获取锁，标记 Bot 为已启动状态")
    
    # 更新共享状态
    update_shared_state("bot_running", True)
    update_shared_state("current_pid", current_pid)
    update_shared_state("last_start_time", time.time())
    
    # 验证是否已有其他 Bot 实例在运行
    try:
        logger.info(f"[PID:{current_pid}] 验证是否已有其他 Bot 实例在运行...")
        bot_info = bot.get_me()
        logger.info(f"[PID:{current_pid}] 验证成功，Bot 可以正常运行：@{bot_info.username}")
        update_shared_state("bot_username", bot_info.username)
        
        # 发送启动消息（只有真正获取到锁的进程才发送）
        try:
            from app.core.telegram.message_sender import send_telegram_message
            from app.core.constants import TELEGRAM_BOT_START_DELAY
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
            update_shared_state("bot_running", False)
            return False
        else:
            logger.warning(f"[PID:{current_pid}] 验证时发生错误，但继续启动：{e}")
    
    # 注册处理器（仅一次）
    register_handlers()
    
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
    
    # 带自动重连的轮询循环
    retry_count = 0
    max_retries = 10
    base_retry_delay = 1
    
    while True:
        try:
            if retry_count > 0:
                logger.info(f"[PID:{current_pid}] 开始第 {retry_count + 1} 次重连尝试...")
            
            # 每次重连前再次检查是否有其他实例在运行
            try:
                # 先尝试获取me信息，这会检测是否有其他实例在运行
                bot_info = bot.get_me()
                logger.info(f"[PID:{current_pid}] 验证成功，Bot 可以正常运行：@{bot_info.username}")
                
                # 额外的409错误预防：在启动轮询前删除可能存在的webhook
                try:
                    bot.delete_webhook()
                    logger.info("再次确认删除 webhook，避免409冲突")
                except Exception as e:
                    logger.warning(f"删除 webhook 时出错：{e}")
                    
            except Exception as e:
                error_msg = str(e)
                if '409' in error_msg or 'Conflict' in error_msg or 'terminated by other getUpdates' in error_msg:
                    logger.error(f"[PID:{current_pid}] 验证失败：检测到其他 Bot 实例正在运行，停止轮询")
                    release_bot_lock()
                    _bot_started = False
                    return False
                else:
                    logger.warning(f"[PID:{current_pid}] 验证时发生错误，但继续启动：{e}")
            
            logger.info("开始 Telegram Bot 长轮询...")
            logger.info("按 Ctrl+C 停止轮询")
            
            # 启动轮询，添加参数以避免409错误
            # 使用 non_stop=True 确保轮询持续运行
            bot.polling(
                none_stop=True,
                interval=0,
                timeout=60,
                allowed_updates=['message', 'callback_query'],
                long_polling_timeout=60  # 长轮询超时时间
            )
            logger.info("轮询已启动并在后台运行")
            
            # 如果正常退出（非异常），重置重试计数
            retry_count = 0
            
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在停止轮询...")
            break
        except Exception as e:
            error_msg = str(e)
            if '409' in error_msg or 'Conflict' in error_msg or 'terminated by other getUpdates' in error_msg:
                logger.error(f"[PID:{current_pid}] 轮询过程中检测到其他 Bot 实例：{e}")
                # 当检测到409错误时，释放锁
                release_bot_lock()
                # 标记 Bot 为未启动状态，避免重复尝试
                _bot_started = False
                # 更新共享状态
                update_shared_state("bot_running", False)
                # 额外的清理：删除锁文件
                try:
                    from app.core.telegram.file_lock import get_default_lock_path
                    lock_path = get_default_lock_path()
                    if lock_path.exists():
                        lock_path.unlink()
                        logger.info(f"[PID:{current_pid}] 已删除锁文件，避免锁文件残留")
                except Exception as cleanup_error:
                    logger.warning(f"[PID:{current_pid}] 清理锁文件时出错：{cleanup_error}")
                logger.info(f"[PID:{current_pid}] 检测到冲突，释放锁并停止轮询")
                return False
            
            logger.error(f"轮询过程中发生错误：{e}", exc_info=True)
            
            # 检查是否需要重连
            retry_count += 1
            if retry_count > max_retries:
                logger.error(f"已达到最大重试次数 ({max_retries})，停止重连")
                break
            
            # 指数退避重连延迟
            retry_delay = min(base_retry_delay * (2 ** (retry_count - 1)), 60)
            logger.info(f"{retry_delay} 秒后尝试重连（{retry_count}/{max_retries}）...")
            time.sleep(retry_delay)
            
            # 重连前停止 polling
            try:
                bot.stop_polling()
                logger.info("已停止轮询，准备重连")
            except Exception as stop_error:
                logger.warning(f"停止轮询时出错：{stop_error}")
    
    # 释放锁
    try:
        release_bot_lock()
        logger.info("Telegram Bot 已停止并释放锁")
    except Exception as e:
        logger.warning(f"释放锁时发生错误：{e}")
    
    # 重置启动状态
    _bot_started = False
    # 更新共享状态
    update_shared_state("bot_running", False)
    
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
    
    # 检查是否已经有 TelegramBot 线程在运行
    for thread in threading.enumerate():
        if thread.name == "TelegramBot":
            logger.info("Telegram Bot 轮询线程已经在运行，跳过重复启动...")
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
