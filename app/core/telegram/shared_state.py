"""
Telegram Bot 共享状态管理
使用文件存储实现跨进程状态共享
"""
import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 与 file_lock 一致：项目根目录 logs/
STATE_FILE = (
    Path(__file__).resolve().parent.parent.parent.parent / "logs" / "telegram_bot_state.json"
)


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def cleanup_stale_shared_state() -> None:
    """进程异常退出后 bot_running 可能残留，启动前清理。"""
    state = get_shared_state()
    pid = state.get("current_pid")
    if not state.get("bot_running"):
        return
    if pid is None or not _is_process_alive(pid):
        logger.info("检测到过期的 Telegram 共享状态，正在重置")
        set_shared_state(
            {
                "bot_initialized": False,
                "bot_running": False,
                "last_start_time": None,
                "current_pid": None,
                "bot_username": None,
            }
        )

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
    检查 Bot 是否正在运行（需 bot_running 且记录中的 PID 仍存活）
    """
    state = get_shared_state()
    if not state.get("bot_running", False):
        return False
    pid = state.get("current_pid")
    if pid is None:
        return False
    if not _is_process_alive(pid):
        logger.info("共享状态中的 Bot PID %s 已不存在，视为未运行", pid)
        return False
    return True