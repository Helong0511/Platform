"""
诊断 Telegram 机器人启动问题
"""
import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('.env')

print("=" * 80)
print("Telegram 机器人启动诊断")
print("=" * 80)

# 1. 检查环境变量
print("\n[步骤 1] 检查环境变量...")
telegram_enable = os.getenv('TELEGRAM_ENABLE', 'false').lower()
telegram_token = os.getenv('TELEGRAM_TOKEN')
telegram_admin = os.getenv('TELEGRAM_ADMIN')

print(f"  TELEGRAM_ENABLE: {telegram_enable}")
print(f"  TELEGRAM_TOKEN: {'已设置' if telegram_token else '未设置'}")
print(f"  TELEGRAM_ADMIN: {'已设置' if telegram_admin else '未设置'}")

if telegram_enable != 'true':
    print("  ❌ Telegram 功能已禁用")
    sys.exit(1)

if not telegram_token:
    print("  ❌ Telegram Token 未设置")
    sys.exit(1)

if not telegram_admin:
    print("  ❌ Telegram Admin 未设置")
    sys.exit(1)

print("  ✅ 环境变量检查通过")

# 2. 检查模块导入
print("\n[步骤 2] 检查模块导入...")
try:
    import telebot
    print("  ✅ telebot 模块导入成功")
except ImportError as e:
    print(f"  ❌ telebot 模块导入失败: {e}")
    sys.exit(1)

# 3. 检查 Bot 初始化
print("\n[步骤 3] 检查 Bot 初始化...")
try:
    bot = telebot.TeleBot(token=telegram_token)
    print("  ✅ Bot 实例创建成功")
except Exception as e:
    print(f"  ❌ Bot 实例创建失败: {e}")
    sys.exit(1)

# 4. 检查 Bot 连接
print("\n[步骤 4] 检查 Bot 连接...")
try:
    bot_info = bot.get_me()
    print(f"  ✅ Bot 连接成功")
    print(f"     Bot ID: {bot_info.id}")
    print(f"     Bot 用户名: @{bot_info.username}")
    print(f"     Bot 名称: {bot_info.first_name}")
except Exception as e:
    print(f"  ❌ Bot 连接失败: {e}")
    sys.exit(1)

# 5. 检查锁文件
print("\n[步骤 5] 检查锁文件状态...")
from pathlib import Path
lock_file_path = Path(__file__).parent / "logs" / "telegram_bot.lock"
print(f"  锁文件路径: {lock_file_path}")

if lock_file_path.exists():
    print("  ⚠️  锁文件已存在")
    try:
        with open(lock_file_path, 'r') as f:
            content = f.read()
        print(f"  锁文件内容:\n{content}")
        
        # 检查进程是否正在运行
        import re
        pid_match = re.search(r'PID:\s*(\d+)', content)
        if pid_match:
            pid = int(pid_match.group(1))
            print(f"  锁文件中的 PID: {pid}")
            
            # 检查进程是否正在运行
            try:
                if os.name == 'nt':  # Windows
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(1, 0, pid)
                    if handle == 0:
                        print("  ⚠️  锁文件中的进程已停止，建议清理锁文件")
                    else:
                        print("  ⚠️  锁文件中的进程正在运行")
                        kernel32.CloseHandle(handle)
            except Exception as e:
                print(f"  无法检查进程状态: {e}")
    except Exception as e:
        print(f"  读取锁文件失败: {e}")
else:
    print("  ✅ 锁文件不存在")

# 6. 检查消息处理器
print("\n[步骤 6] 检查消息处理器...")
try:
    # 注册测试处理器
    @bot.message_handler(commands=['test'])
    def test_command(message):
        bot.reply_to(message, "✅ 测试命令响应成功")
    
    print(f"  ✅ 消息处理器注册成功")
    print(f"     已注册处理器数量: {len(bot.message_handlers)}")
except Exception as e:
    print(f"  ❌ 消息处理器注册失败: {e}")
    sys.exit(1)

# 7. 发送测试消息
print("\n[步骤 7] 发送测试消息...")
try:
    test_message = "🧪 Telegram 机器人诊断测试\n\n" \
                 "✅ 环境变量检查通过\n" \
                 "✅ 模块导入成功\n" \
                 "✅ Bot 初始化成功\n" \
                 "✅ Bot 连接成功\n" \
                 "✅ 消息处理器注册成功\n" \
                 "✅ 测试消息发送成功\n\n" \
                 "Telegram 机器人工作正常！"
    
    bot.send_message(chat_id=telegram_admin, text=test_message)
    print(f"  ✅ 测试消息发送成功到: {telegram_admin}")
except Exception as e:
    print(f"  ❌ 测试消息发送失败: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("所有诊断步骤通过！Telegram 机器人工作正常。")
print("=" * 80)
print("\n建议:")
print("1. 如果锁文件存在且进程已停止，请手动删除锁文件")
print("2. 确保应用正在运行，Telegram 机器人才能正常工作")
print("3. 检查应用日志，查看 Telegram 机器人启动信息")
