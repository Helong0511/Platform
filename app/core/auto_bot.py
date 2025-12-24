#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author    : 贺鉴龙
# @File      : auto_bot.py
# @Time      : 2025/9/18 11:58
# @IDE       : PyCharm
# @Function  :
import os
import logging  # 日志记录模块
import re
import threading
import sys
from pathlib import Path
from app.core.config import settings  # 应用配置
from app.core.utils import get_app_now  # 应用时区时间获取函数

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


def get_chat_id_handler(message):
    """获取聊天ID处理器（已废弃，使用 /id 命令）"""
    if not _check_bot_available():
        logger.error("Bot 未初始化，无法处理消息")
        return

    chat_id = message.chat.id
    bot.reply_to(message, f"你的聊天ID是: {chat_id}")


# 注册命令处理器（确保在 Bot 初始化后注册）
def _register_command_handlers():
    """注册所有命令处理器"""
    if not bot_initialized or not TELEBOT_AVAILABLE or not bot:
        logger.warning("Bot 未初始化，无法注册命令处理器")
        return False
    
    try:
        @bot.message_handler(commands=['test'])
        def handle_test_command(message):
            """处理 /test 命令：显示测试内联按钮"""
            if not _check_bot_available():
                logger.error("Bot 未初始化，无法处理消息")
                return

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
            if not _check_bot_available():
                logger.error("Bot 未初始化，无法处理消息")
                return

            chat_id = message.chat.id
            markup = InlineKeyboardMarkup()

            markup.row(InlineKeyboardButton(text='打卡', callback_data='clock'))
            markup.row(InlineKeyboardButton(text='取消', callback_data='Cancel'))

            bot.send_message(chat_id, "确认是否要打卡？", reply_markup=markup)
        
        @bot.message_handler(commands=['id'])
        def get_chat_id(message):
            """处理 /id 命令：返回聊天ID"""
            logger.info(f"收到 /id 命令，来自用户: {message.from_user.username or message.from_user.first_name}")
            if not _check_bot_available():
                logger.error("Bot 未初始化，无法处理消息")
                return
            try:
                chat_id = message.chat.id
                bot.reply_to(message, f"你的聊天ID是: {chat_id}")
                logger.info(f"成功回复 /id 命令，聊天ID: {chat_id}")
            except Exception as e:
                logger.error(f"处理 /id 命令时发生错误: {e}", exc_info=True)
                try:
                    bot.reply_to(message, "处理命令时发生错误，请稍后重试")
                except:
                    pass
        
        logger.info("Telegram Bot 命令处理器注册成功: /id, /test, /clock")
        return True
    except Exception as e:
        logger.error(f"注册命令处理器时发生错误: {e}", exc_info=True)
        return False

# 如果 Bot 已初始化，立即注册命令处理器
if bot_initialized and TELEBOT_AVAILABLE:
    _register_command_handlers()

# 处理按钮点击事件
if bot_initialized and TELEBOT_AVAILABLE:
    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
        """处理内联按钮回调查询"""
        if not _check_bot_available():
            logger.error("Bot 未初始化，无法处理回调查询")
            return

        try:
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
        # 先测试 Bot 连接
        try:
            bot_info = bot.get_me()
            logger.info(f"Telegram Bot 连接成功: @{bot_info.username} (ID: {bot_info.id})")
        except Exception as test_error:
            logger.error(f"Telegram Bot 连接测试失败: {test_error}", exc_info=True)
            logger.error("请检查 TELEGRAM_TOKEN 是否正确，以及网络连接是否正常")
            return
        
        logger.info("开始轮询 Telegram 更新...")
        bot.infinity_polling(
            allowed_updates=[  # 明确指定需要处理的更新类型
                "message",  # 处理消息
                "callback_query",  # 处理回调查询（按钮点击）
                "inline_query",  # 处理内联查询（搜索框）
                "chosen_inline_result",  # 处理选择的内联结果
                "shipping_query",  # 处理货运查询
                "pre_checkout_query",  # 处理预结账查询
                "poll",  # 处理投票
                "poll_answer",  # 处理投票答案
                "my_chat_member",  # 添加成员状态更新，用于检测机器人被添加/删除
                "chat_member",  # 添加群组成员变动监控
                "edited_message",  # 处理编辑过的消息
                "channel_post",  # 处理频道帖子
                "edited_channel_post"  # 处理编辑过的频道帖子
            ],
            timeout=20,  # 设置超时时间
            long_polling_timeout=20  # 长轮询超时时间
        )
    except KeyboardInterrupt:
        logger.info("收到终止信号，正在优雅关闭机器人...")
    except telebot.apihelper.ApiException as api_error:
        logger.error(f"Telegram API 错误: {api_error}", exc_info=True)
        logger.error(f"API 错误详情: {type(api_error).__name__}: {str(api_error)}")
    except Exception as e:
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
        # 确保命令处理器已注册
        logger.info(f"[PID:{current_pid}] 正在注册命令处理器...")
        if not _register_command_handlers():
            logger.warning(f"[PID:{current_pid}] 命令处理器注册失败，但将继续启动 Bot")
        
        logger.info(f"[PID:{current_pid}] 正在设置 Telegram Bot 命令...")
        # 设置 Bot 命令
        commands_list = [
            ("id", "查询聊天ID"),
            ("test", "测试内联按钮"),
            ("clock", "打卡")
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
            except Exception as e:
                logger.warning(f"[PID:{current_pid}] 设置 Telegram Bot 命令时发生错误: {e}")

        # 启动轮询线程（守护线程，主进程退出时自动退出）
        logger.info(f"[PID:{current_pid}] 正在启动 Telegram Bot 轮询线程...")
        bot_thread = threading.Thread(target=run_bot, daemon=True, name="TelegramBot")
        bot_thread.start()
        
        # 等待一小段时间，检查线程是否正常启动
        import time
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


# /id 命令处理器已在 _register_command_handlers() 中注册


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

        # pyTelegramBotAPI 的 send_message 是同步的，需要在线程中执行
        # 使用 asyncio 来避免阻塞异步事件循环
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: bot.send_message(chat_id=chat_id.strip(), text=message)
        )
        logger.info(f"Telegram消息发送成功: {chat_id}")
        return True
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
