"""
⚠️ 警告：此文件已重构！

auto_bot.py 已拆分为 telegram 子模块，此文件仅保留向后兼容的导入

新模块位置：app/core/telegram/
- bot_initializer.py - Bot 初始化
- bot_state.py - 全局状态
- command_handlers/ - 命令处理器
- callback_handlers/ - 回调处理器
- message_sender.py - 消息发送
- file_lock.py - 文件锁管理
- polling_manager.py - 轮询管理
- notification_templates.py - 通知模板

请使用新的导入路径：
    from app.core.telegram import initialize_bot, send_telegram_message
"""
import logging
import warnings

logger = logging.getLogger(__name__)

# 发出弃用警告
warnings.warn(
    "app.core.auto_bot 已重构为 app.core.telegram 子模块，"
    "请更新导入路径：from app.core.telegram import ...",
    DeprecationWarning,
    stacklevel=2
)

# 向后兼容：从新模块导入所有公开接口
try:
    from app.core.telegram import (
        # Bot 初始化和状态
        initialize_bot,
        get_bot,
        is_bot_available,
        bot,
        bot_initialized,
        TELEBOT_AVAILABLE,
        get_bot_status_info,
        
        # 消息发送
        send_telegram_message,
        send_telegram_message_with_buttons,
        send_admin_notification,
        
        # 通知模板
        ConversionNotificationTemplate,
        SystemNotificationTemplate,
        StatisticsNotificationTemplate,
    )
    
    # 文件锁管理
    from app.core.telegram.file_lock import (
        acquire_bot_lock,
        release_bot_lock,
        is_lock_held
    )
    
    # 轮询管理
    from app.core.telegram.polling_manager import (
        start_polling,
        start_bot_thread,
        set_bot_commands
    )
    
    logger.info("✅ 已从新模块导入 Telegram Bot 功能（向后兼容）")
    
except ImportError as e:
    logger.error(f"❌ 从新模块导入失败：{e}")
    logger.error("请确保 app/core/telegram/ 目录存在且包含所有必要的模块")
    
    # 如果导入失败，定义空函数避免崩溃
    bot = None
    bot_initialized = False
    TELEBOT_AVAILABLE = False
    
    def initialize_bot():
        logger.error("Bot 初始化功能不可用")
        return None, False, False
    
    def get_bot():
        return None
    
    def is_bot_available():
        return False
    
    def send_telegram_message(*args, **kwargs):
        logger.error("消息发送功能不可用")
        return False
    
    def send_telegram_message_with_buttons(*args, **kwargs):
        logger.error("消息发送功能不可用")
        return False, None
    
    def send_admin_notification(*args, **kwargs):
        logger.error("通知发送功能不可用")
        return False
    
    def acquire_bot_lock(*args, **kwargs):
        return False
    
    def release_bot_lock():
        pass
    
    def start_polling():
        logger.error("轮询功能不可用")
        return False
    
    def start_bot_thread():
        logger.error("线程启动功能不可用")
        return False
    
    def get_bot_status_info():
        logger.error("Bot 状态查询功能不可用")
        return {
            "token_configured": False,
            "admin_configured": False,
            "bot_thread_alive": False,
            "connection_test": "未测试"
        }

# 导出所有公开接口
__all__ = [
    # Bot 初始化和状态
    'initialize_bot',
    'get_bot',
    'is_bot_available',
    'bot',
    'bot_initialized',
    'TELEBOT_AVAILABLE',
    'get_bot_status_info',
    
    # 消息发送
    'send_telegram_message',
    'send_telegram_message_with_buttons',
    'send_admin_notification',
    
    # 通知模板
    'ConversionNotificationTemplate',
    'SystemNotificationTemplate',
    'StatisticsNotificationTemplate',
    
    # 文件锁管理
    'acquire_bot_lock',
    'release_bot_lock',
    'is_lock_held',
    
    # 轮询管理
    'start_polling',
    'start_bot_thread',
    'set_bot_commands',
]
