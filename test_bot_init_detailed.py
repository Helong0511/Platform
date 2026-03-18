#!/usr/bin/env python3
"""
详细测试 Bot 初始化过程
"""
import os
import sys
import logging

# 添加项目路径
sys.path.insert(0, '/data/Platform')

# 设置详细的日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s'
)

print("=" * 80)
print("详细测试 Bot 初始化过程")
print("=" * 80)

# 1. 测试 telebot 模块导入
print("\n[步骤 1] 测试 telebot 模块导入...")
try:
    import telebot
    print("  ✅ telebot 模块导入成功")
    print(f"  telebot 版本: {telebot.__version__ if hasattr(telebot, '__version__') else '未知'}")
except ImportError as e:
    print(f"  ❌ telebot 模块导入失败: {e}")
    sys.exit(1)

# 2. 测试 telebot 子模块导入
print("\n[步骤 2] 测试 telebot 子模块导入...")
try:
    from telebot import types
    print("  ✅ telebot.types 导入成功")
except ImportError as e:
    print(f"  ❌ telebot.types 导入失败: {e}")
    sys.exit(1)

try:
    from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
    print("  ✅ telebot.types 类导入成功")
except ImportError as e:
    print(f"  ❌ telebot.types 类导入失败: {e}")
    sys.exit(1)

# 3. 测试 settings 加载
print("\n[步骤 3] 测试 settings 加载...")
try:
    from dotenv import load_dotenv
    load_dotenv('/data/Platform/.env')
    
    from app.core.config import settings
    print(f"  ✅ settings 加载成功")
    print(f"  TELEGRAM_ENABLE: {settings.TELEGRAM_ENABLE}")
    print(f"  TELEGRAM_TOKEN: {'已设置' if settings.TELEGRAM_TOKEN else '未设置'}")
    print(f"  TELEGRAM_ADMIN: {settings.TELEGRAM_ADMIN}")
except Exception as e:
    print(f"  ❌ settings 加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 4. 测试 Bot 创建
print("\n[步骤 4] 测试 Bot 创建...")
try:
    token = settings.TELEGRAM_TOKEN
    if token:
        print(f"  Token: {token[:10]}...")
        bot = telebot.TeleBot(token=token)
        print(f"  ✅ Bot 创建成功: {bot}")
        
        # 测试 Bot 连接
        info = bot.get_me()
        print(f"  ✅ Bot 连接成功: @{info.username}")
    else:
        print(f"  ❌ Token 未设置")
except Exception as e:
    print(f"  ❌ Bot 创建失败: {e}")
    import traceback
    traceback.print_exc()

# 5. 测试 bot_initializer 模块导入
print("\n[步骤 5] 测试 bot_initializer 模块导入...")
try:
    # 清理可能的状态
    import app.core.telegram.bot_state as bot_state_module
    if hasattr(bot_state_module, '_bot_instance'):
        bot_state_module._bot_instance = None
    if hasattr(bot_state_module, '_bot_instance_created'):
        bot_state_module._bot_instance_created = False
    if hasattr(bot_state_module, 'bot_initialized'):
        bot_state_module.bot_initialized = False
    
    # 导入 bot_initializer（这会自动调用 initialize_bot）
    from app.core.telegram import bot_initializer
    print(f"  ✅ bot_initializer 导入成功")
    print(f"  bot_instance: {bot_initializer.bot_instance}")
    print(f"  initialized: {bot_initializer.initialized}")
    print(f"  available: {bot_initializer.available}")
except Exception as e:
    print(f"  ❌ bot_initializer 导入失败: {e}")
    import traceback
    traceback.print_exc()

# 6. 再次检查 bot_state
print("\n[步骤 6] 再次检查 bot_state...")
try:
    from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE
    print(f"  bot: {bot}")
    print(f"  bot_initialized: {bot_initialized}")
    print(f"  TELEBOT_AVAILABLE: {TELEBOT_AVAILABLE}")
except Exception as e:
    print(f"  ❌ 检查 bot_state 失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)
