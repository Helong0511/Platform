"""
Telegram Bot 状态管理接口
"""
from fastapi import APIRouter, Depends, Request

from app.core.audit_log import log_user_action, commit_audit_log
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import require_admin
from app.core.telegram.bot_state import get_bot_status_info
from app.core.telegram.polling_manager import start_bot_thread
from app.core.telegram.shared_state import get_shared_state
from app.models.models import User
from app.schemas.base import ResponseBaseSchema
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

router = APIRouter()


@router.get("/telegram/status", response_model=ResponseBaseSchema[dict])
async def get_telegram_status():
    """获取 Telegram Bot 状态"""
    status_info = get_bot_status_info()
    shared_state = get_shared_state()

    return ResponseBaseSchema.success(
        data={
            "bot_status": status_info,
            "shared_state": shared_state,
        },
        message="查询成功",
    )


@router.post("/telegram/restart", response_model=ResponseBaseSchema[dict])
async def restart_telegram_bot(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """重启 Telegram Bot"""
    try:
        success = start_bot_thread()
        await log_user_action(
            db=db,
            action_type="TASK_RUN",
            user=current_user,
            resource_type="SYSTEM",
            resource_id=0,
            resource_name="Telegram Bot重启",
            request=request,
            details={"restarted": success},
        )
        await commit_audit_log(db)
        if success:
            return ResponseBaseSchema.success(
                data={"restarted": True},
                message="Telegram Bot 重启命令已发送",
            )
        return ResponseBaseSchema.success(
            data={"restarted": False},
            message="Telegram Bot 已经在运行",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise_api_exception(
            ErrorCode.INTERNAL_ERROR,
            detail=f"重启失败：{str(e)}",
        )
