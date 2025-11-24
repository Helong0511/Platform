#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author    : 贺鉴龙
# @File      : auto_bot.py
# @Time      : 2025/9/18 11:58
# @IDE       : PyCharm
# @Function  :
import datetime
import json
import os
import logging  # 日志记录模块
import re

import telebot  # pip3 install --upgrade pyTelegramBotAPI
from telebot import types
from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
import threading
from app.core.config import settings  # 应用配置
from app.core.database import AsyncSessionLocal  # 异步数据库会话工厂
from sqlalchemy import select  # SQLAlchemy查询构建器

logger = logging.getLogger(__name__)
bot = None
bot_initialized = False  # 添加初始化状态标志

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


def get_chat_id_handler(message):
    if not bot_initialized:
        logger.error("Bot 未初始化，无法处理消息")
        return

    chat_id = message.chat.id
    bot.reply_to(message, f"你的聊天ID是: {chat_id}")


if bot_initialized:
    @bot.message_handler(commands=['test'])
    def handle_bot_click(message):
        if not bot_initialized:
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

if bot_initialized:
    @bot.message_handler(commands=['clock'])
    def handle_bot_click(message):
        if not bot_initialized:
            logger.error("Bot 未初始化，无法处理消息")
            return

        chat_id = message.chat.id
        markup = InlineKeyboardMarkup()

        markup.row(InlineKeyboardButton(text='打卡', callback_data='clock'))

        # 第四行：一个按钮（取消）
        markup.row(InlineKeyboardButton(text='取消', callback_data='Cancel'))

        bot.send_message(chat_id, "确认是否要打卡？", reply_markup=markup)

# 处理按钮点击事件
if bot_initialized:
    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
        if call.data == "View":
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="你点击了查看按钮"
            )
        elif call.data == "clock":
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"打卡成功！时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        elif call.data == "Cancel":
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="你取消了操作")
            bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        else:
            bot.answer_callback_query(callback_query_id=call.id, text="未知操作")

if bot_initialized:
    @bot.message_handler(content_types=["photo"])
    def handle_image(message):
        if not bot_initialized:
            logger.error("Bot 未初始化，无法处理消息")
            return

        bot.reply_to(message, "收到图片！")


def run_bot():
    if not bot_initialized:
        logger.error("Bot 未初始化，无法启动轮询")
        return

    try:
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
            ]
        )
    except KeyboardInterrupt:
        logger.error("收到终止信号，正在优雅关闭机器人...")
    except telebot.apihelper.ApiException as api_error:
        logger.error(f"Telegram API 错误: {api_error}")
    except Exception as e:
        logger.error(f"机器人运行时发生错误: {str(e)}")
    finally:
        logger.error("机器人已停止运行")


def start_bot():
    """启动 Telegram Bot 轮询线程"""
    if not bot_initialized:
        logger.error("Bot 未初始化，无法启动")
        return False

    if not bot:
        logger.error("Bot 对象不存在，无法启动")
        return False

    try:
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
                logger.info("Telegram Bot 命令设置成功")
            except Exception as e:
                logger.warning(f"设置 Telegram Bot 命令时发生错误: {e}")

        # 启动轮询线程（守护线程，主进程退出时自动退出）
        bot_thread = threading.Thread(target=run_bot, daemon=True, name="TelegramBot")
        bot_thread.start()
        logger.info("Telegram Bot 轮询线程已启动")
        return True
    except Exception as e:
        logger.error(f"启动 Telegram Bot 时发生错误: {e}", exc_info=True)
        return False


def stop_bot():
    """停止 Telegram Bot 轮询"""
    if bot_initialized and bot:
        try:
            bot.stop_polling()
            logger.info("Telegram Bot 轮询已停止")
        except Exception as e:
            logger.error(f"停止 Telegram Bot 时发生错误: {e}", exc_info=True)


if bot_initialized:
    @bot.message_handler(commands=['id'])
    def gei_chat_id(message):
        if not bot_initialized:
            logger.error("Bot 未初始化，无法处理消息")
            return
        bot.reply_to(message, f"{message.chat.id}")


async def send_telegram_message(message: str, chat_id: str | None = None):
    """
    发送 Telegram 消息
    
    Args:
        message: 要发送的消息内容
        chat_id: 目标聊天ID（可选，默认使用配置中的 TELEGRAM_ADMIN）
    
    Returns:
        bool: 发送是否成功
    """
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
        # 使用 threading 来避免阻塞异步事件循环
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: bot.send_message(chat_id=chat_id.strip(), text=message)
        )
        logger.info(f"Telegram消息发送成功: {chat_id}")
        return True
    except telebot.apihelper.ApiException as api_error:
        logger.error(f"发送Telegram消息失败（API错误）: {api_error}")
        return False
    except Exception as e:
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
if bot_initialized:
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
