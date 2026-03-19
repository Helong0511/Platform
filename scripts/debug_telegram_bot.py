"""
Telegram Bot 调试脚本

全面诊断 Bot 不响应指令的问题
"""
import sys
import time
import logging
from pathlib import Path

# 设置日志配置
log_file = Path(__file__).parent.parent / "logs" / "telegram_debug.log"
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
    print("🔍 Telegram Bot 调试脚本")
    print("=" * 80)
    
    try:
        # 1. 检查模块导入
        logger.info("1. 检查模块导入...")
        try:
            import telebot
            logger.info("✅ pyTelegramBotAPI 模块导入成功")
        except ImportError as e:
            logger.error(f"❌ pyTelegramBotAPI 模块导入失败: {e}")
            print("\n❌ 请安装 pyTelegramBotAPI: pip install pyTelegramBotAPI")
            sys.exit(1)
        
        # 2. 检查配置
        logger.info("2. 检查配置...")
        from app.core.config import settings
        
        logger.info(f"Telegram 功能启用: {settings.TELEGRAM_ENABLE}")
        logger.info(f"Telegram Token 配置: {settings.TELEGRAM_TOKEN[:4]}****" if settings.TELEGRAM_TOKEN else "None")
        logger.info(f"Telegram Admin 配置: {settings.TELEGRAM_ADMIN}")
        
        if not settings.TELEGRAM_ENABLE:
            logger.error("❌ Telegram 功能已禁用")
            print("\n❌ 请在 .env 文件中设置 TELEGRAM_ENABLE=true")
            sys.exit(1)
        
        if not settings.TELEGRAM_TOKEN:
            logger.error("❌ Telegram Token 未配置")
            print("\n❌ 请在 .env 文件中设置 TELEGRAM_TOKEN")
            sys.exit(1)
        
        # 3. 检查 Bot 初始化
        logger.info("3. 检查 Bot 初始化...")
        from app.core.telegram.bot_initializer import initialize_bot, is_bot_available
        from app.core.telegram.bot_state import get_bot_state, get_bot_status_info
        
        bot_instance, initialized, available = initialize_bot()
        logger.info(f"初始化结果: 实例={bot_instance is not None}, 状态={initialized}, 可用={available}")
        
        bot_state = get_bot_state()
        logger.info(f"Bot 状态: {bot_state}")
        
        status_info = get_bot_status_info()
        logger.info(f"详细状态: {status_info}")
        
        if not initialized:
            logger.error("❌ Bot 初始化失败")
            print("\n❌ Bot 初始化失败，请检查配置和网络连接")
            sys.exit(1)
        
        # 4. 检查处理器注册
        logger.info("4. 检查处理器注册...")
        from app.core.telegram.polling_manager import register_handlers, _handlers_registered
        
        register_handlers()
        logger.info(f"处理器注册状态: {_handlers_registered}")
        
        if hasattr(bot_instance, 'message_handlers'):
            handler_count = len(bot_instance.message_handlers)
            logger.info(f"消息处理器数量: {handler_count}")
            for i, handler in enumerate(bot_instance.message_handlers):
                logger.info(f"  处理器 {i+1}: {handler}")
        
        # 5. 检查轮询线程
        logger.info("5. 检查轮询线程...")
        from app.core.telegram.polling_manager import start_bot_thread, _bot_started
        
        import threading
        telegram_threads = [t for t in threading.enumerate() if t.name == "TelegramBot"]
        logger.info(f"Telegram 线程数量: {len(telegram_threads)}")
        
        for thread in telegram_threads:
            logger.info(f"  线程: {thread.name}, 活跃: {thread.is_alive()}")
        
        if not _bot_started and not telegram_threads:
            logger.info("启动轮询线程...")
            success = start_bot_thread()
            logger.info(f"轮询线程启动: {success}")
        
        # 6. 测试 Bot 连接
        logger.info("6. 测试 Bot 连接...")
        try:
            bot_info = bot_instance.get_me()
            logger.info(f"✅ Bot 连接成功: @{bot_info.username}")
            print(f"\n✅ Bot 信息: @{bot_info.username}")
        except Exception as e:
            logger.error(f"❌ Bot 连接失败: {e}")
            print(f"\n❌ Bot 连接失败: {e}")
        
        # 7. 检查共享状态
        logger.info("7. 检查共享状态...")
        from app.core.telegram.shared_state import get_shared_state
        
        shared_state = get_shared_state()
        logger.info(f"共享状态: {shared_state}")
        
        # 8. 检查锁文件
        logger.info("8. 检查锁文件...")
        from app.core.telegram.file_lock import get_default_lock_path
        
        lock_path = get_default_lock_path()
        logger.info(f"锁文件路径: {lock_path}")
        logger.info(f"锁文件存在: {lock_path.exists()}")
        
        # 9. 模拟消息处理测试
        logger.info("9. 测试消息处理...")
        from telebot.types import Message
        
        # 创建模拟消息对象
        class MockMessage:
            def __init__(self):
                self.text = "/id"
                self.chat = type('obj', (object,), {'id': 123456789, 'type': 'private'})
                self.from_user = type('obj', (object,), {'id': 123456789, 'first_name': 'Test', 'username': 'testuser'})
                self.message_id = 1
        
        mock_message = MockMessage()
        
        # 测试 id 命令处理器
        try:
            from app.core.telegram.command_handlers.id_command import get_chat_id
            logger.info("测试 /id 命令处理器...")
            get_chat_id(mock_message)
            logger.info("✅ /id 命令处理器测试通过")
        except Exception as e:
            logger.error(f"❌ /id 命令处理器测试失败: {e}")
        
        # 测试 start 命令处理器
        try:
            from app.core.telegram.command_handlers.start_command import cmd_start
            logger.info("测试 /start 命令处理器...")
            cmd_start(mock_message)
            logger.info("✅ /start 命令处理器测试通过")
        except Exception as e:
            logger.error(f"❌ /start 命令处理器测试失败: {e}")
        
        # 测试 help 命令处理器
        try:
            from app.core.telegram.command_handlers.help_command import cmd_help
            logger.info("测试 /help 命令处理器...")
            cmd_help(mock_message)
            logger.info("✅ /help 命令处理器测试通过")
        except Exception as e:
            logger.error(f"❌ /help 命令处理器测试失败: {e}")
        
        # 10. 最终状态
        logger.info("10. 最终状态检查...")
        final_status = get_bot_status_info()
        logger.info(f"最终状态: {final_status}")
        
        print("\n" + "=" * 80)
        print("📋 调试结果汇总:")
        print("=" * 80)
        print(f"✅ 模块导入: {'成功' if available else '失败'}")
        print(f"✅ 配置检查: {'通过' if settings.TELEGRAM_TOKEN else '失败'}")
        print(f"✅ Bot 初始化: {'成功' if initialized else '失败'}")
        print(f"✅ 处理器注册: {'成功' if _handlers_registered else '失败'}")
        print(f"✅ 轮询线程: {'运行中' if telegram_threads else '未启动'}")
        print(f"✅ Bot 连接: {'成功' if '成功' in status_info['connection_test'] else '失败'}")
        
        print("\n🔧 建议操作:")
        print("1. 确保只有一个 Bot 实例在运行")
        print("2. 检查 Telegram API 连接")
        print("3. 验证命令格式是否正确")
        print("4. 查看 logs/telegram_debug.log 获取详细信息")
        print("5. 在 Telegram 中测试 /id 命令")
        
    except Exception as e:
        logger.error(f"❌ 调试过程中发生错误: {e}", exc_info=True)
        print(f"\n❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
