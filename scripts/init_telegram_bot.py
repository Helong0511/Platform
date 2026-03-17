"""
手动初始化 Telegram Bot 脚本

强制重新加载模块并初始化 Bot
"""
import sys
import importlib
import logging

# 设置日志级别
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 确保可以导入 app 模块
sys.path.insert(0, '.')

# 强制重新加载模块
def reload_modules():
    """强制重新加载相关模块"""
    logger.info("开始重新加载模块...")
    
    # 移除已导入的模块
    for module in list(sys.modules.keys()):
        if module.startswith('app.core.telegram'):
            del sys.modules[module]
    
    logger.info("模块已移除，准备重新导入")

if __name__ == "__main__":
    print("=" * 80)
    print("🤖 Telegram Bot 手动初始化脚本")
    print("=" * 80)
    
    # 重新加载模块
    reload_modules()
    
    try:
        # 导入并初始化
        from app.core.telegram.bot_initializer import initialize_bot
        from app.core.telegram.bot_state import get_bot_state
        
        print("\n🔄 正在初始化 Telegram Bot...")
        bot_instance, initialized, available = initialize_bot()
        
        print(f"\n✅ 初始化结果:")
        print(f"  Bot 实例: {bot_instance is not None}")
        print(f"  初始化状态: {initialized}")
        print(f"  模块可用: {available}")
        
        # 获取详细状态
        state = get_bot_state()
        print(f"\n📋 详细状态:")
        for key, value in state.items():
            print(f"  {key}: {value}")
        
        # 测试连接
        if bot_instance:
            print("\n🌐 测试 Telegram API 连接...")
            try:
                me = bot_instance.get_me()
                print(f"✅ 连接成功！")
                print(f"  Bot ID: {me.id}")
                print(f"  Bot 名称: {me.first_name}")
                print(f"  Bot 用户名: @{me.username}")
            except Exception as e:
                print(f"❌ 连接失败: {e}")
        
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
