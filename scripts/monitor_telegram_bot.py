"""
Telegram Bot 实时监控脚本

监控 Bot 轮询状态和消息处理
"""
import sys
import time
import logging
from pathlib import Path

# 设置日志配置
log_file = Path(__file__).parent.parent / "logs" / "telegram_monitor.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 确保可以导入 app 模块
sys.path.insert(0, '.')

if __name__ == "__main__":
    print("=" * 80)
    print("🔍 Telegram Bot 实时监控")
    print("=" * 80)
    
    try:
        # 导入必要的模块
        from app.core.telegram.bot_initializer import initialize_bot, is_bot_available
        from app.core.telegram.bot_state import get_bot_state, get_bot_status_info
        from app.core.telegram.polling_manager import start_bot_thread, _bot_started
        from app.core.telegram.shared_state import get_shared_state
        from app.core.telegram.file_lock import get_default_lock_path, is_lock_held
        
        # 初始化 Bot
        logger.info("初始化 Bot...")
        bot_instance, initialized, available = initialize_bot()
        
        if not initialized:
            logger.error("Bot 初始化失败")
            print("\n❌ Bot 初始化失败，请检查配置")
            sys.exit(1)
        
        # 启动轮询线程
        if not _bot_started:
            logger.info("启动轮询线程...")
            success = start_bot_thread()
            if not success:
                logger.error("轮询线程启动失败")
                print("\n❌ 轮询线程启动失败")
                sys.exit(1)
        
        # 实时监控
        print("\n🔄 开始实时监控...")
        print("按 Ctrl+C 停止监控")
        print("=" * 80)
        
        import threading
        
        for i in range(60):  # 监控 60 秒
            # 检查 Bot 状态
            bot_state = get_bot_state()
            status_info = get_bot_status_info()
            shared_state = get_shared_state()
            
            # 检查轮询线程
            telegram_threads = [t for t in threading.enumerate() if t.name == "TelegramBot"]
            thread_status = "运行中" if telegram_threads else "未运行"
            
            # 检查锁状态
            lock_path = get_default_lock_path()
            lock_exists = lock_path.exists()
            lock_held = is_lock_held()
            
            # 检查处理器
            handler_count = 0
            if hasattr(bot_instance, 'message_handlers'):
                handler_count = len(bot_instance.message_handlers)
            
            # 打印状态
            print(f"\r[{i+1}/60] Bot 状态: 初始化={bot_state['bot_initialized']}, 线程={thread_status}, 处理器={handler_count}, 锁={lock_held}", end="")
            
            # 记录详细状态
            logger.info(f"监控状态 #{i+1}: Bot初始化={bot_state['bot_initialized']}, 线程={thread_status}, 处理器={handler_count}, 锁={lock_held}, 连接测试={status_info['connection_test']}")
            logger.info(f"共享状态: {shared_state}")
            
            # 检查是否有新的日志
            if i % 5 == 0:
                # 检查 app.log 中的 Telegram 消息
                app_log = Path(__file__).parent.parent / "logs" / "app.log"
                if app_log.exists():
                    with open(app_log, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()[-50:]  # 读取最后 50 行
                    telegram_lines = [line for line in lines if 'telegram' in line.lower() or 'bot' in line.lower() or 'message' in line.lower()]
                    for line in telegram_lines:
                        if '收到消息' in line or '命令处理器' in line:
                            logger.info(f"新消息: {line.strip()}")
            
            time.sleep(1)
        
        print("\n" + "=" * 80)
        print("📋 监控结果汇总:")
        print("=" * 80)
        
        final_state = get_bot_state()
        final_status = get_bot_status_info()
        final_shared = get_shared_state()
        
        print(f"✅ Bot 初始化: {final_state['bot_initialized']}")
        print(f"✅ 模块可用: {final_state['TELEBOT_AVAILABLE']}")
        print(f"✅ 连接测试: {final_status['connection_test']}")
        print(f"✅ 轮询线程: {'运行中' if [t for t in threading.enumerate() if t.name == 'TelegramBot'] else '未运行'}")
        print(f"✅ 处理器数量: {len(bot_instance.message_handlers) if hasattr(bot_instance, 'message_handlers') else 0}")
        print(f"✅ 共享状态: {final_shared}")
        
        print("\n🔧 建议操作:")
        print("1. 检查 logs/app.log 中的消息处理日志")
        print("2. 确认 Bot 有发送消息的权限")
        print("3. 验证命令格式是否正确（私聊直接发送，群组需要 @botname）")
        print("4. 检查网络连接和 Telegram API 访问")
        print("5. 查看 logs/telegram_monitor.log 获取详细监控信息")
        
    except Exception as e:
        logger.error(f"监控过程中发生错误: {e}", exc_info=True)
        print(f"\n❌ 监控失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
