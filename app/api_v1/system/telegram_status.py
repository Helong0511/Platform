"""
Telegram Bot 状态管理接口
"""
from fastapi import APIRouter, HTTPException
from app.core.telegram.bot_state import get_bot_status_info
from app.core.telegram.shared_state import get_shared_state
from app.core.telegram.polling_manager import start_bot_thread

router = APIRouter()

@router.get("/telegram/status")
async def get_telegram_status():
    """
    获取 Telegram Bot 状态
    """
    status_info = get_bot_status_info()
    shared_state = get_shared_state()
    
    return {
        "status": "success",
        "data": {
            "bot_status": status_info,
            "shared_state": shared_state
        }
    }

@router.post("/telegram/restart")
async def restart_telegram_bot():
    """
    重启 Telegram Bot
    """
    try:
        # 启动 Bot 线程
        success = start_bot_thread()
        if success:
            return {
                "status": "success",
                "message": "Telegram Bot 重启命令已发送"
            }
        else:
            return {
                "status": "info",
                "message": "Telegram Bot 已经在运行"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重启失败：{str(e)}")