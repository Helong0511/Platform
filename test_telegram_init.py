#!/usr/bin/env python3
"""
测试 Telegram 机器人配置和初始化
"""
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, '/data/Platform')

print("=" * 80)
print("Telegram 机器人配置和初始化测试")
print("=" * 80)

# 1. 检查环境变量
print("\n[步骤 1] 检查环境变量...")
from dotenv import load_dotenv
load_dotenv('/data/Platform/.env')

telegram_enable = os.getenv('TELEGRAM_ENABLE')
telegram_token = os.getenv('TELEGRAM_TOKEN')
telegram_admin = os.getenv('TELEGRAM_ADMIN')

print(f"  TELEGRAM_ENABLE: {telegram_enable}")
print(f"  TELEGRAM_TOKEN: {'已设置' if telegram_token else '未设置'}")
print(f"  TELEGRAM_ADMIN: {'已设置' if telegram_admin else '未设置'}")

# 2. 检查 settings 对象
print("\n[步骤 2] 检查 settings 对象...")
try:
    from app.core.config import settings
    print(f"  settings.TELEGRAM_ENABLE: {settings.TELEGRAM_ENABLE}")
    print(f"  settings.TELEGRAM_TOKEN: {'已设置' if settings.TELEGRAM_TOKEN else '未设置'}")
    print(f"  settings.TELEGRAM_ADMIN: {settings.TELEGRAM_ADMIN}")
    
    # 测试 getattr 访问
    telegram_enabled_getattr = getattr(settings, 'TELEGRAM_ENABLE', True)
    print(f"  getattr(settings, 'TELEGRAM_ENABLE', True): {telegram_enabled_getattr}")
except Exception as e:
    print(f"  ❌ 检查 settings 失败: {e}")
    import traceback
    traceback.print_exc()

# 3. 测试模块导入
print("\n[步骤 3] 测试模块导入...")
try:
    import telebot
    print("  ✅ telebot 模块导入成功")
except ImportError as e:
    print(f"  ❌ telebot 模块导入失败: {e}")
    sys.exit(1)

# 4. 测试 Bot 初始化
print("\n[步骤 4] 测试 Bot 初始化...")
try:
    from app.core.telegram.bot_initializer import initialize_bot
    bot_instance, initialized, available = initialize_bot()
    print(f"  Bot 实例: {bot_instance}")
    print(f"  初始化状态: {initialized}")
    print(f"  模块可用: {available}")
except Exception as e:
    print(f"  ❌ Bot 初始化失败: {e}")
    import traceback
    traceback.print_exc()

# 5. 测试 bot_state
print("\n[步骤 5] 测试 bot_state...")
try:
    from app.core.telegram.bot_state import bot_initialized
    print(f"  bot_initialized: {bot_initialized}")
except Exception as e:
    print(f"  ❌ 检查 bot_state 失败: {e}")
    import traceback
    traceback.print_exc()

# 6. 测试锁文件
print("\n[步骤 6] 测试锁文件...")
try:
    from app.core.telegram.file_lock import acquire_bot_lock, release_bot_lock, is_lock_held
    print(f"  is_lock_held(): {is_lock_held()}")
    
    # 尝试获取锁
    lock_acquired = acquire_bot_lock()
    print(f"  acquire_bot_lock(): {lock_acquired}")
    
    if lock_acquired:
        print(f"  ✅ 成功获取锁")
        # 释放锁
        release_bot_lock()
        print(f"  ✅ 已释放锁")
    else:
        print(f"  ❌ 无法获取锁（其他进程可能已持有）")
except Exception as e:
    print(f"  ❌ 测试锁文件失败: {e}")
    import traceback
    traceback.print_exc()

# 7. 测试 start_bot_thread
print("\n[步骤 7] 测试 start_bot_thread...")
try:
    from app.core.telegram.polling_manager import start_bot_thread
    print(f"  start_bot_thread() 函数存在")
    
    # 注意：这里不实际调用，因为它会启动一个无限循环
    # 只是测试函数是否可以正常导入
except Exception as e:
    print(f"  ❌ 测试 start_bot_thread 失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)
