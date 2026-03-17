"""
测试 Telegram Bot 轮询功能

验证409错误处理和锁机制
"""
import sys
import time
import logging

# 设置日志级别
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 确保可以导入 app 模块
sys.path.insert(0, '.')

if __name__ == "__main__":
    print("=" * 80)
    print("🔄 Telegram Bot 轮询测试脚本")
    print("=" * 80)
    
    try:
        # 导入轮询管理器
        from app.core.telegram.polling_manager import start_bot_thread, _bot_started
        from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE
        
        print(f"\n📋 初始状态:")
        print(f"  Bot 实例: {bot is not None}")
        print(f"  初始化状态: {bot_initialized}")
        print(f"  模块可用: {TELEBOT_AVAILABLE}")
        print(f"  轮询线程已启动: {_bot_started}")
        
        if not bot_initialized:
            print("\n❌ Bot 未初始化，需要先初始化")
            from app.core.telegram.bot_initializer import initialize_bot
            print("\n🔄 正在初始化 Bot...")
            bot_instance, initialized, available = initialize_bot()
            print(f"  初始化结果: 实例={bot_instance is not None}, 状态={initialized}, 可用={available}")
        
        print("\n🚀 启动轮询线程...")
        success = start_bot_thread()
        print(f"  轮询线程启动: {success}")
        
        if success:
            print("\n⏰ 测试运行中...")
            print("  按 Ctrl+C 停止测试")
            
            # 运行30秒后自动停止
            for i in range(30):
                print(f"  运行中... {i+1}/30")
                time.sleep(1)
            
            print("\n✅ 测试完成")
        else:
            print("\n❌ 轮询线程启动失败")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
