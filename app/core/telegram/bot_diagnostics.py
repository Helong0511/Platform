"""
Telegram Bot 诊断工具

提供超级详细的 Bot 初始化状态检查
"""
import logging
import sys
import os
import importlib
from typing import Dict, Any, List

from app.core.config import settings, detect_production_env, is_production_env_name
from app.core.telegram.bot_state import (
    bot, bot_initialized, 
    _bot_instance_created, _bot_lock_file, _bot_lock_acquired
)
from app.core.telegram.bot_initializer import initialize_bot

logger = logging.getLogger(__name__)


class TelegramBotDiagnostics:
    """Telegram Bot 诊断工具"""
    
    @staticmethod
    def get_super_detailed_status() -> Dict[str, Any]:
        """
        获取超级详细的 Bot 状态信息
        
        Returns:
            Dict[str, Any]: 详细的状态信息
        """
        status = {
            "general": {},
            "module": {},
            "configuration": {},
            "initialization": {},
            "network": {},
            "system": {},
            "recommendations": []
        }
        
        # 1. 通用信息
        status["general"] = TelegramBotDiagnostics._check_general_info()
        
        # 2. 模块检查
        status["module"] = TelegramBotDiagnostics._check_module()
        
        # 3. 配置检查
        status["configuration"] = TelegramBotDiagnostics._check_configuration()
        
        # 4. 初始化状态检查
        status["initialization"] = TelegramBotDiagnostics._check_initialization()
        
        # 5. 网络连接检查
        status["network"] = TelegramBotDiagnostics._check_network()
        
        # 6. 系统环境检查
        status["system"] = TelegramBotDiagnostics._check_system()
        
        # 7. 生成建议
        status["recommendations"] = TelegramBotDiagnostics._generate_recommendations(status)
        
        return status
    
    @staticmethod
    def _check_general_info() -> Dict[str, Any]:
        """检查通用信息"""
        return {
            "python_version": sys.version,
            "os_platform": sys.platform,
            "working_directory": os.getcwd(),
            "python_path": sys.path
        }
    
    @staticmethod
    def _check_module() -> Dict[str, Any]:
        """检查模块状态"""
        module_status = {
            "telebot_available": False,
            "import_status": "未知"
        }
        
        try:
            import telebot
            module_status["import_status"] = "成功"
            module_status["telebot_version"] = getattr(telebot, "__version__", "未知")
            module_status["telebot_available"] = True
        except ImportError as e:
            module_status["import_status"] = f"失败: {str(e)}"
        except Exception as e:
            module_status["import_status"] = f"错误: {str(e)}"
        
        return module_status
    
    @staticmethod
    def _check_configuration() -> Dict[str, Any]:
        """检查配置状态"""
        config_status = {
            "telegram_enable": getattr(settings, 'TELEGRAM_ENABLE', True),
            "telegram_token_configured": False,
            "telegram_admin_configured": False,
            "telegram_chat_id_configured": False
        }
        
        # 检查 Token（已按环境解析为 LOCAL / PRODUCTION / 回退值）
        telegram_token = getattr(settings, 'TELEGRAM_TOKEN', None)
        if telegram_token:
            config_status["telegram_token_configured"] = True
            config_status["token_length"] = len(telegram_token)
            config_status["token_prefix"] = telegram_token[:4] + "****" if len(telegram_token) > 4 else telegram_token
            config_status["token_bot_id"] = (
                telegram_token.split(":", 1)[0] if ":" in telegram_token else None
            )
            is_prod = is_production_env_name(detect_production_env())
            env_key = "TELEGRAM_TOKEN_PRODUCTION" if is_prod else "TELEGRAM_TOKEN_LOCAL"
            if os.getenv(env_key) and str(os.getenv(env_key)).strip():
                config_status["token_source"] = env_key
            elif os.getenv("TELEGRAM_TOKEN") and str(os.getenv("TELEGRAM_TOKEN")).strip():
                config_status["token_source"] = "TELEGRAM_TOKEN"
            else:
                config_status["token_source"] = "unknown"
        
        # 检查管理员
        telegram_admin = getattr(settings, 'TELEGRAM_ADMIN', None)
        if telegram_admin:
            config_status["telegram_admin_configured"] = True
            config_status["admin_value"] = telegram_admin
        
        # 检查聊天ID
        telegram_chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)
        if telegram_chat_id:
            config_status["telegram_chat_id_configured"] = True
            config_status["chat_id_value"] = telegram_chat_id
        
        return config_status
    
    @staticmethod
    def _check_initialization() -> Dict[str, Any]:
        """检查初始化状态"""
        init_status = {
            "bot_initialized": bot_initialized,
            "bot_instance": bot is not None,
            "bot_instance_created": _bot_instance_created,
            "lock_file": _bot_lock_file,
            "lock_acquired": _bot_lock_acquired
        }
        
        # 尝试重新初始化以测试
        try:
            test_bot, test_initialized, test_available = initialize_bot()
            init_status["reinitialize_result"] = {
                "bot": test_bot is not None,
                "initialized": test_initialized,
                "available": test_available
            }
        except Exception as e:
            init_status["reinitialize_error"] = str(e)
        
        return init_status
    
    @staticmethod
    def _check_network() -> Dict[str, Any]:
        """检查网络连接"""
        network_status = {
            "connection_test": "未测试",
            "api_accessible": False
        }
        
        # 动态检查模块可用性
        try:
            importlib.import_module("telebot")
            telebot_available = True
        except ImportError:
            telebot_available = False
        
        if bot_initialized and telebot_available and bot:
            try:
                me = bot.get_me()
                network_status["connection_test"] = "成功"
                network_status["api_accessible"] = True
                network_status["bot_info"] = {
                    "id": me.id,
                    "first_name": me.first_name,
                    "username": me.username
                }
            except Exception as e:
                network_status["connection_test"] = f"失败: {str(e)}"
                network_status["api_accessible"] = False
        
        return network_status
    
    @staticmethod
    def _check_system() -> Dict[str, Any]:
        """检查系统环境"""
        system_status = {
            "env_vars": {},
            "file_permissions": {}
        }
        
        # 检查环境变量
        for key in os.environ:
            if "TELEGRAM" in key.upper():
                system_status["env_vars"][key] = os.environ[key]
        
        # 检查文件权限
        lock_file_path = getattr(settings, 'TELEGRAM_BOT_LOCK_FILE', None)
        if lock_file_path:
            try:
                if os.path.exists(lock_file_path):
                    system_status["file_permissions"]["lock_file"] = {
                        "exists": True,
                        "readable": os.access(lock_file_path, os.R_OK),
                        "writable": os.access(lock_file_path, os.W_OK)
                    }
                else:
                    system_status["file_permissions"]["lock_file"] = {
                        "exists": False
                    }
            except Exception as e:
                system_status["file_permissions"]["lock_file_error"] = str(e)
        
        return system_status
    
    @staticmethod
    def _generate_recommendations(status: Dict[str, Any]) -> List[str]:
        """生成修复建议"""
        recommendations = []
        
        # 模块相关建议
        if not status["module"]["telebot_available"]:
            recommendations.append("安装 pyTelegramBotAPI 模块: pip install pyTelegramBotAPI")
        
        # 配置相关建议
        config = status["configuration"]
        if not config["telegram_enable"]:
            recommendations.append("在配置中启用 Telegram Bot: TELEGRAM_ENABLE=true")
        if not config["telegram_token_configured"]:
            recommendations.append(
                "配置 Telegram Bot Token: TELEGRAM_TOKEN_LOCAL（本机）/"
                "TELEGRAM_TOKEN_PRODUCTION（生产），或兼容项 TELEGRAM_TOKEN"
            )
        if not config["telegram_admin_configured"]:
            recommendations.append("配置 Telegram 管理员 Chat ID: TELEGRAM_ADMIN=your_chat_id")
        
        # 初始化相关建议
        init = status["initialization"]
        if not init["bot_initialized"]:
            recommendations.append("重新初始化 Bot: 调用 initialize_bot() 函数")
        if "reinitialize_error" in init:
            recommendations.append(f"初始化错误: {init['reinitialize_error']}")
        
        # 网络相关建议
        network = status["network"]
        if not network["api_accessible"]:
            recommendations.append("检查网络连接和 Telegram API 访问权限")
            recommendations.append("确保服务器可以访问 https://api.telegram.org")
        
        # 系统相关建议
        system = status["system"]
        if not system["file_permissions"]:
            recommendations.append("确保 Bot 锁文件有正确的读写权限")
        
        return recommendations
    
    @staticmethod
    def print_detailed_report():
        """打印详细的诊断报告"""
        print("=" * 80)
        print("🔍 Telegram Bot 超级详细诊断报告")
        print("=" * 80)
        
        status = TelegramBotDiagnostics.get_super_detailed_status()
        
        # 打印通用信息
        print("\n📋 通用信息")
        print("-" * 40)
        for key, value in status["general"].items():
            print(f"{key}: {value}")
        
        # 打印模块状态
        print("\n🧩 模块状态")
        print("-" * 40)
        for key, value in status["module"].items():
            print(f"{key}: {value}")
        
        # 打印配置状态
        print("\n⚙️ 配置状态")
        print("-" * 40)
        for key, value in status["configuration"].items():
            print(f"{key}: {value}")
        
        # 打印初始化状态
        print("\n🚀 初始化状态")
        print("-" * 40)
        for key, value in status["initialization"].items():
            print(f"{key}: {value}")
        
        # 打印网络状态
        print("\n🌐 网络状态")
        print("-" * 40)
        for key, value in status["network"].items():
            print(f"{key}: {value}")
        
        # 打印系统状态
        print("\n💻 系统状态")
        print("-" * 40)
        for key, value in status["system"].items():
            print(f"{key}: {value}")
        
        # 打印建议
        print("\n💡 建议")
        print("-" * 40)
        if status["recommendations"]:
            for i, recommendation in enumerate(status["recommendations"], 1):
                print(f"{i}. {recommendation}")
        else:
            print("✅ 所有检查都通过了！")
        
        print("\n" + "=" * 80)
    
    @staticmethod
    def check_bot_health() -> bool:
        """
        检查 Bot 是否健康
        
        Returns:
            bool: Bot 是否健康
        """
        status = TelegramBotDiagnostics.get_super_detailed_status()
        
        # 检查关键指标
        is_healthy = all([
            status["module"]["telebot_available"],
            status["configuration"]["telegram_token_configured"],
            status["initialization"]["bot_initialized"],
            status["network"]["api_accessible"]
        ])
        
        return is_healthy


if __name__ == "__main__":
    TelegramBotDiagnostics.print_detailed_report()
