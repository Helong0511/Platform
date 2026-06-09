"""
上游 API 广告数据导入公共流程模块。

功能说明：
- 抽取各上游定时任务（Pomiad、Addermobi、Skymobi 等）共用的「拉数后入库」收尾逻辑
- 可选预处理（匹配数修正、字段回退）→ ``process_api_ad_data`` 去重写入 → 提交事务
- 写入 task_result_store 摘要；有新增/更新时异步发送 Telegram 通知

在系统中的位置：
- 被 ``tasks/*_task.py`` 在 fetch_*_rows 完成后调用

注意事项：
1. 事务失败须 rollback 后再 set_task_result，避免部分提交
2. Telegram 通知失败不回滚入库，保证数据优先
3. 预处理回调为可选 Callable，上游特殊逻辑勿写入本模块
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Mapping, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ad_data_processor import process_api_ad_data
from app.core.telegram import send_telegram_message_async
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
    """
    上游导入收尾：提交事务、记录任务结果、可选 Telegram 通知。

    在 process_api_ad_data 返回统计结果后调用；提交失败会回滚并向上抛出异常。

    参数:
        db: 当前异步数据库会话（由调用方持有，本函数负责 commit/rollback）
        result: process_api_ad_data 返回的统计字典（inserted/updated/skipped/error_count）
        task_name: 任务名称，用于写入 task_result_store
        current_time_str: 已格式化的执行时间字符串，用于通知正文
        notify_title: Telegram 通知标题中的上游名称（如「Pomiad」）

    返回:
        格式化后的结果摘要字符串（插入/更新/跳过/错误条数）
    """
    # ---------- 事务提交 ----------
    try:
        logger.info("开始提交主事务...")
        await db.commit()
        logger.info("主事务提交成功")
    except Exception as commit_error:
        await db.rollback()
        logger.error(f"数据提交失败，已回滚: {commit_error}", exc_info=True)
        raise Exception(f"数据提交失败: {commit_error}") from commit_error

    # ---------- 汇总统计 ----------
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

    # ---------- Telegram 通知（仅在有实际写入时发送） ----------
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
            # 5 秒超时，避免通知阻塞调度器主流程
            await asyncio.wait_for(send_telegram_message_async(telegram_msg), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning(f"发送 Telegram 通知超时: {task_name}")

    # ---------- 写入任务结果供调度器持久化 ----------
    set_task_result(task_name, f"执行成功: {result_summary}")
    return result_summary


def preprocess_addermobi_match_counts(ad_data: List[Any]) -> List[Any]:
    """
    Addermobi 数据预处理：修正匹配广告请求数。

    部分上游返回 MatchedAdRequests=0 但 AdRequestsCoverage 非零，
    此时按「请求数 × 覆盖率」推算匹配数，避免入库后指标异常。

    参数:
        ad_data: API 原始行列表（就地修改 MatchedAdRequests 字段）

    返回:
        处理后的同一列表引用
    """
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
                # 字段无法转为数值时跳过该行
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
    标准上游拉数入库入口：预处理 → process_api_ad_data → 提交与通知。

    各上游定时任务在 fetch_* 拿到行列表后，传入字段映射与本函数即可完成入库。
    data 为空时仅记录「暂无产品数据」并返回，不开启数据库事务。

    参数:
        task_name: 任务名称（与 task_names 常量一致）
        data: 上游 API 返回的原始行列表
        field_mapping: 上游字段名 → 库表字段名的映射
        source: 数据来源标识，写入广告明细（如「Pomiad定时任务」）
        current_time_str: 执行时间字符串，用于通知
        notify_title: Telegram 通知中的上游显示名
        data_transform: 可选预处理函数（如 Addermobi 匹配数修正、Pomiad domain 回退）
    """
    # ---------- 空数据快速返回 ----------
    if not data:
        logger.info("暂无产品数据")
        set_task_result(task_name, "执行成功: 暂无产品数据")
        return

    # ---------- 可选数据预处理 ----------
    if data_transform:
        data = data_transform(list(data))

    # ---------- 入库主流程 ----------
    async with AsyncSessionLocal() as db:
        # 广告数据处理需要关联管理员用户（审计/归属）
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
