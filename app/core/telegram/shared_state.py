"""
Telegram Bot 共享状态管理
使用文件存储实现跨进程状态共享
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 状态文件路径
STATE_FILE = Path(__file__).parent.parent.parent / "logs" / "telegram_bot_state.json"

def get_shared_state() -> Dict[str, Any]:
    """
    获取共享状态
    
    Returns:
        Dict[str, Any]: 共享状态字典
    """
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"读取共享状态失败：{e}")
    
    return {
        "bot_initialized": False,
        "bot_running": False,
        "last_start_time": None,
        "current_pid": None,
        "bot_username": None
    }

def set_shared_state(state: Dict[str, Any]):
    """
    设置共享状态
    
    Args:
        state: 状态字典
    """
    try:
        # 确保目录存在
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"写入共享状态失败：{e}")

def update_shared_state(key: str, value: Any):
    """
    更新共享状态的单个键值
    
    Args:
        key: 键名
        value: 值
    """
    state = get_shared_state()
    state[key] = value
    set_shared_state(state)

def is_bot_running() -> bool:
    """
    检查Bot是否正在运行
    
    Returns:
        bool: Bot是否正在运行
    """
    state = get_shared_state()
    return state.get("bot_running", False)