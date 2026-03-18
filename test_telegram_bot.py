"""
测试 Telegram 机器人连接和功能
"""
import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('.env')

# 获取配置
telegram_token = os.getenv('TELEGRAM_TOKEN')
telegram_admin = os.getenv('TELEGRAM_ADMIN')
telegram_enable = os.getenv('TELEGRAM_ENABLE', 'true')

print("=" * 60)
print("Telegram 机器人测试")
print("=" * 60)
print(f"Telegram 启用状态: {telegram_enable}")
print(f"Telegram Token: {telegram_token[:10] if telegram_token else 'None'}...")
print(f"Telegram Admin: {telegram_admin}")
print("=" * 60)

# 测试 1: 导入 telebot 模块
print("\n[测试 1] 导入 telebot 模块...")
try:
    import telebot
    print("✓ telebot 模块导入成功")
except ImportError as e:
    print(f"✗ telebot 模块导入失败: {e}")
    sys.exit(1)

# 测试 2: 创建 Bot 实例
print("\n[测试 2] 创建 Bot 实例...")
try:
    bot = telebot.TeleBot(token=telegram_token)
    print("✓ Bot 实例创建成功")
except Exception as e:
    print(f"✗ Bot 实例创建失败: {e}")
    sys.exit(1)

# 测试 3: 测试 Bot 连接
print("\n[测试 3] 测试 Bot 连接...")
try:
    bot_info = bot.get_me()
    print(f"✓ Bot 连接成功")
    print(f"  Bot ID: {bot_info.id}")
    print(f"  Bot 用户名: @{bot_info.username}")
    print(f"  Bot 名称: {bot_info.first_name}")
except Exception as e:
    print(f"✗ Bot 连接失败: {e}")
    sys.exit(1)

# 测试 4: 发送测试消息
print("\n[测试 4] 发送测试消息...")
if telegram_admin:
    try:
        test_message = "🧪 Telegram 机器人测试消息\n\n" \
                     "✓ 模块导入成功\n" \
                     "✓ Bot 实例创建成功\n" \
                     "✓ Bot 连接成功\n" \
                     "✓ 消息发送成功\n\n" \
                     "Telegram 机器人工作正常！"
        
        bot.send_message(chat_id=telegram_admin, text=test_message)
        print(f"✓ 测试消息发送成功到: {telegram_admin}")
    except Exception as e:
        print(f"✗ 测试消息发送失败: {e}")
        sys.exit(1)
else:
    print("✗ 未配置 TELEGRAM_ADMIN，跳过消息发送测试")

print("\n" + "=" * 60)
print("所有测试通过！Telegram 机器人工作正常。")
print("=" * 60)
