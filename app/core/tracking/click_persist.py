"""
点击是否落库 clicks 表（令牌模式下可关闭以减负）。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks

from app.core.config import settings

logger = logging.getLogger(__name__)


def describe_click_persist_mode() -> str:
    """人类可读的点击落库策略说明（用于启动日志）。"""
    explicit = os.getenv("PERSIST_CLICKS_TO_DB", "").strip().lower()
    token_on = bool(getattr(settings, "USE_TRACKING_TOKEN", False))
    if explicit in ("true", "1", "yes"):
        base = "强制写库 (PERSIST_CLICKS_TO_DB=true)"
    elif explicit in ("false", "0", "no"):
        base = "强制不写库 (PERSIST_CLICKS_TO_DB=false)"
    elif token_on:
        base = "默认不写库 (USE_TRACKING_TOKEN=true, 未设 PERSIST_CLICKS_TO_DB)"
    else:
        base = "默认写库 (USE_TRACKING_TOKEN=false)"
    if token_on:
        return f"{base}；click_id=追踪令牌"
    return f"{base}；click_id=时间戳随机"


def log_click_persist_mode_at_startup() -> None:
    logger.info("点击落库策略: %s", describe_click_persist_mode())


def should_persist_clicks_to_db() -> bool:
    """
    是否将点击写入 clicks 表。

    - PERSIST_CLICKS_TO_DB=true/false 显式覆盖
    - 未设置时：USE_TRACKING_TOKEN=true 默认不写库（Postback 靠令牌 + 转化快照）
    - USE_TRACKING_TOKEN=false 时默认写库（与升级前一致）
    """
    explicit = os.getenv("PERSIST_CLICKS_TO_DB", "").strip().lower()
    if explicit in ("true", "1", "yes"):
        return True
    if explicit in ("false", "0", "no"):
        return False
    return not bool(getattr(settings, "USE_TRACKING_TOKEN", False))


async def persist_click_record(
    click_data: Dict[str, Any],
    background_tasks: Optional[BackgroundTasks] = None,
) -> None:
    """Redis 队列优先，失败则后台任务写 clicks 表；令牌模式可整体跳过。"""
    if not should_persist_clicks_to_db():
        logger.debug(
            "跳过 clicks 表写入（令牌归因）: click_id=%s",
            click_data.get("click_id"),
        )
        return

    from app.core.clicks_queue import enqueue_click
    from app.api_v1.tracking.tracking import create_click_background
    from app.core.utils import get_app_now_naive

    enqueued = await enqueue_click(click_data)
    if not enqueued and background_tasks is not None:
        click_data["click_time"] = get_app_now_naive()
        background_tasks.add_task(create_click_background, click_data)
