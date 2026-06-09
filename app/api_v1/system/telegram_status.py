"""Telegram Bot 状态与重启 API

职责：查询 Bot 运行状态、共享内存状态；管理员可触发后台线程重启。

权限：
- GET  /telegram/status   任意调用方可查状态（路由层未强制登录，供监控使用）
- POST /telegram/restart  仅管理员。

说明：系统运维接口，含定时任务、审计日志、会话、缓存、斗篷与敏感路径探测。"""
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
    """
    查询 Telegram Bot 运行状态。

    返回 bot_status（线程存活、最近轮询时间等）与 shared_state（内存共享状态）。
    供监控面板或运维脚本探测，路由层未强制登录。
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


@router.post("/telegram/restart", response_model=ResponseBaseSchema[dict])
async def restart_telegram_bot(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    重启 Telegram Bot 后台轮询线程。

    权限：仅管理员。
    流程：调用 start_bot_thread 启动新线程；若已在运行则返回 restarted=False。
    操作写入审计日志（action_type=TASK_RUN）。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
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
        # ---------- 条件分支 ----------
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
