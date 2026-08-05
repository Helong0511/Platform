"""
广告数据健康巡检定时任务：

1. 每天 00:30 冻结昨天标准（日期+产品+来源）
2. 每天 01:00 跑完整健康巡检（缺数/断档/昨有今无/日环比/倒扣vs标准）
"""
from __future__ import annotations

import logging
from datetime import timedelta

from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now
from app.scheduler_module.task_names import (
    AD_DATA_BASELINE_FREEZE_TASK_NAME,
    AD_DATA_HEALTH_SCAN_TASK_NAME,
)
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import get_current_time_str, log_task_start
from app.services.ad_data import baseline_service as bs
from app.services.ad_data.health_runner import run_daily_health_scan

logger = logging.getLogger(__name__)


async def ad_data_baseline_freeze_task() -> None:
    """冻结昨天广告数据标准快照。"""
    log_task_start(AD_DATA_BASELINE_FREEZE_TASK_NAME)
    today = get_app_now().date()
    yesterday = today - timedelta(days=1)
    try:
        async with AsyncSessionLocal() as db:
            result = await bs.freeze_baseline_for_date(
                db, stat_date=yesterday, force=False
            )
            await db.commit()
        msg = (
            f"执行成功: 冻结 {result.get('stat_date')} "
            f"inserted={result.get('inserted')} skipped={result.get('skipped')} "
            f"batch={result.get('batch_id')} @ {get_current_time_str()}"
        )
        logger.info("[%s] %s", AD_DATA_BASELINE_FREEZE_TASK_NAME, msg)
        set_task_result(AD_DATA_BASELINE_FREEZE_TASK_NAME, msg)
    except Exception as exc:
        err = f"执行失败: {exc}"
        logger.error("[%s] %s", AD_DATA_BASELINE_FREEZE_TASK_NAME, err, exc_info=True)
        set_task_result(AD_DATA_BASELINE_FREEZE_TASK_NAME, err)
        raise


async def ad_data_health_scan_task() -> None:
    """日级健康巡检并可选 Telegram。"""
    log_task_start(AD_DATA_HEALTH_SCAN_TASK_NAME)
    try:
        async with AsyncSessionLocal() as db:
            result = await run_daily_health_scan(db)
            await db.commit()
        msg = (
            f"执行成功: alerts={result.get('report_alerts')} "
            f"baseline_drops={result.get('baseline_drop_alerts')} "
            f"persisted={result.get('persisted_scan_alerts')} "
            f"telegram={result.get('telegram_sent')} @ {get_current_time_str()}"
        )
        logger.info("[%s] %s", AD_DATA_HEALTH_SCAN_TASK_NAME, msg)
        set_task_result(AD_DATA_HEALTH_SCAN_TASK_NAME, msg)
    except Exception as exc:
        err = f"执行失败: {exc}"
        logger.error("[%s] %s", AD_DATA_HEALTH_SCAN_TASK_NAME, err, exc_info=True)
        set_task_result(AD_DATA_HEALTH_SCAN_TASK_NAME, err)
        raise
