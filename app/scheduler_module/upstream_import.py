"""
上游 API 广告数据导入公共流程（提交、通知、任务结果）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Mapping, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ad_data_processor import process_api_ad_data
from app.core.auto_bot import send_telegram_message
from app.core.database import AsyncSessionLocal
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import format_result_summary, get_admin_user

logger = logging.getLogger(__name__)


async def finalize_upstream_import(
    db: AsyncSession,
    result: Dict[str, Any],
    *,
    task_name: str,
    current_time_str: str,
    notify_title: str,
) -> str:
    """提交事务、写任务结果，可选 Telegram 通知。返回结果摘要字符串。"""
    try:
        logger.info("开始提交主事务...")
        await db.commit()
        logger.info("主事务提交成功")
    except Exception as commit_error:
        await db.rollback()
        logger.error(f"数据提交失败，已回滚: {commit_error}", exc_info=True)
        raise Exception(f"数据提交失败: {commit_error}") from commit_error

    inserted_count = result.get("inserted_count", 0)
    updated_count = result.get("updated_count", 0)
    skipped_count = result.get("skipped_count", 0)
    error_count = result.get("error_count", 0)

    result_summary = format_result_summary(
        inserted=inserted_count,
        updated=updated_count,
        skipped=skipped_count,
        error=error_count,
    )
    logger.info(f"数据导入完成: {result_summary}")

    if inserted_count > 0 or updated_count > 0:
        telegram_msg = (
            f"⏰ {notify_title} 定时任务执行完成\n\n"
            f"执行时间: {current_time_str}\n"
            f"✅ 成功插入: {inserted_count} 条\n"
            f"✅ 成功更新: {updated_count} 条"
        )
        if skipped_count > 0:
            telegram_msg += f"\n⏭️ 跳过重复: {skipped_count} 条"
        if error_count > 0:
            telegram_msg += f"\n❌ 错误: {error_count} 条"
        try:
            await asyncio.wait_for(send_telegram_message(telegram_msg), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning(f"发送 Telegram 通知超时: {task_name}")

    set_task_result(task_name, f"执行成功: {result_summary}")
    return result_summary


def preprocess_addermobi_match_counts(ad_data: List[Any]) -> List[Any]:
    """匹配数为 0 但覆盖率非 0 时，按 请求数×覆盖率 修正 MatchedAdRequests。"""
    for item in ad_data:
        try:
            match_count = item.get("MatchedAdRequests", 0) or 0
            request_count = item.get("AdRequests", 0) or 0
            coverage_rate = item.get("AdRequestsCoverage", 0) or 0
            try:
                match_count = float(match_count) if match_count else 0
                request_count = float(request_count) if request_count else 0
                coverage_rate = float(coverage_rate) if coverage_rate else 0
            except (ValueError, TypeError):
                continue
            if match_count == 0 and coverage_rate != 0 and request_count > 0:
                item["MatchedAdRequests"] = int(request_count * coverage_rate)
        except Exception as e:
            logger.warning("Addermobi 预处理数据项失败: %s", e)
    return ad_data


async def import_upstream_ad_data(
    *,
    task_name: str,
    data: List[Any],
    field_mapping: Mapping[str, str],
    source: str,
    current_time_str: str,
    notify_title: str,
    data_transform: Optional[Callable[[List[Any]], List[Any]]] = None,
) -> None:
    """
    标准上游拉数入库：process_api_ad_data + 提交 + 任务结果。
    data 为空时记「暂无产品数据」并返回。
    """
    if not data:
        logger.info("暂无产品数据")
        set_task_result(task_name, "执行成功: 暂无产品数据")
        return

    if data_transform:
        data = data_transform(list(data))

    async with AsyncSessionLocal() as db:
        admin_user = await get_admin_user(db)
        if not admin_user:
            logger.error("未找到管理员用户，无法处理产品，跳过本次任务")
            set_task_result(task_name, "跳过: 未找到管理员用户")
            return

        result = await process_api_ad_data(
            data=data,
            db=db,
            admin_user=admin_user,
            source=source,
            field_mapping=dict(field_mapping),
        )
        await finalize_upstream_import(
            db,
            result,
            task_name=task_name,
            current_time_str=current_time_str,
            notify_title=notify_title,
        )
