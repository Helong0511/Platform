"""Telegram Bot 运行时状态与重启 API

职责：查询 Bot 轮询线程/共享内存状态；管理员可触发后台线程重启。

挂载前缀：``/telegram``（见 ``app.api_v1.__init__``）。
与 ``app.api_v1.external.telegram`` 的 ``GET /telegram/status``（配置态摘要）并存，本模块使用独立路径避免冲突。

权限：
- GET  /telegram/runtime-status  仅管理员可查状态
- POST /telegram/restart         仅管理员。

说明：系统运维接口，含定时任务、审计日志、会话、缓存、斗篷与敏感路径探测。"""
import asyncio

from fastapi import APIRouter, Depends, Request

from app.core.audit_log import log_user_action, commit_audit_log
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import require_admin
from app.core.telegram.bot_state import get_bot_status_info
from app.core.telegram.polling_manager import restart_bot_thread
from app.core.telegram.shared_state import get_shared_state
from app.models.models import User
from app.schemas.base import ResponseBaseSchema
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

router = APIRouter()


@router.get("/runtime-status", response_model=ResponseBaseSchema[dict])
async def get_telegram_status(
    current_user: User = Depends(require_admin),
):
    """
    查询 Telegram Bot 运行时状态（轮询线程 + 共享内存）。

    返回 bot_status（线程存活、最近轮询时间等）与 shared_state（内存共享状态）。
    供管理员监控面板或运维脚本探测。
    配置态摘要请用 GET /telegram/status（external.telegram，需管理员）。
    """
    status_info = get_bot_status_info()
    shared_state = get_shared_state()

    return ResponseBaseSchema.success(
        data={
            "bot_status": status_info,
            "shared_state": shared_state,
        },
        message="查询成功",
    )


@router.post("/restart", response_model=ResponseBaseSchema[dict])
async def restart_telegram_bot(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    真正重启 Telegram Bot 后台轮询：先停 Application，再启新线程。

    权限：仅管理员。操作写入审计日志（action_type=TASK_RUN）。
    """
    try:
        result = await asyncio.to_thread(restart_bot_thread)
        await log_user_action(
            db=db,
            action_type="TASK_RUN",
            user=current_user,
            resource_type="SYSTEM",
            resource_id=0,
            resource_name="Telegram Bot重启",
            request=request,
            details=result,
        )
        await commit_audit_log(db)
        if result.get("restarted"):
            return ResponseBaseSchema.success(
                data=result,
                message="Telegram Bot 已重启",
            )
        return ResponseBaseSchema.success(
            data=result,
            message="Telegram Bot 重启未完成（未能启动新轮询线程）",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise_api_exception(
            ErrorCode.INTERNAL_ERROR,
            detail=f"重启失败：{str(e)}",
        )
