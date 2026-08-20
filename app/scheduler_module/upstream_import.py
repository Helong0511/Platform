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

import logging
from collections.abc import Mapping
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ad_data_processor import process_api_ad_data, send_pending_data_decrease_warnings
from app.core.ad_data_metadata import format_report_type_counts_for_notify
from app.core.product_assignment import format_assignment_gap_telegram_message
from app.core.telegram import send_telegram_notify_async
from app.services.ad_data.dual_dimension_check import (
    format_country_unit_mismatch_telegram_message,
)
from app.core.database import AsyncSessionLocal
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import (
    format_notify_params_block,
    format_result_summary,
    get_admin_user,
    merge_notify_params_with_fetch_stats,
)
from app.services.ad_data.query_cache import invalidate_ad_data_query_caches

logger = logging.getLogger(__name__)


async def finalize_upstream_import(
    db: AsyncSession,
    result: Dict[str, Any],
    *,
    task_name: str,
    current_time_str: str,
    notify_title: str,
    update_task_result: bool = True,
    notify_params: Optional[Mapping[str, Any]] = None,
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
        notify_params: 可选任务参数（如起始/终止日期），展示在 Telegram 通知中

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

    # 入库成功后失效筛选项/汇总缓存，避免管理端产品下拉仍显示旧列表
    if int(result.get("inserted_count") or 0) > 0 or int(result.get("updated_count") or 0) > 0:
        try:
            await invalidate_ad_data_query_caches(
                reason=f"upstream_import:{notify_title or task_name}"
            )
        except Exception as cache_exc:
            logger.warning("上游入库后清理广告数据查询缓存失败: %s", cache_exc)

    await send_pending_data_decrease_warnings(
        traffic_decreases=result.get("traffic_decreases") or [],
        metric_decreases=result.get("metric_decreases") or [],
    )

    # 倒扣：入库后对已冻结的历史日，现库汇总 vs 日标准（请求数+收益扣前）
    if int(result.get("inserted_count") or 0) > 0 or int(result.get("updated_count") or 0) > 0:
        try:
            from datetime import timedelta

            from app.core.utils import get_app_now
            from app.services.ad_data import baseline_service as baseline_svc
            from app.core.telegram_utils import split_long_message

            today = get_app_now().date()
            touched = [today - timedelta(days=1), today - timedelta(days=2)]
            baseline_alerts = await baseline_svc.compare_frozen_dates_after_import(
                db,
                touched_dates=touched,
                today=today,
                data_source=str(result.get("data_source") or "") or None,
            )
            if baseline_alerts:
                await db.commit()
                cfg = await baseline_svc.load_settings_view(db)
                if cfg.enable_telegram:
                    msg = baseline_svc.format_baseline_drop_telegram(baseline_alerts)
                    if msg:
                        for part in split_long_message(msg):
                            await send_telegram_notify_async(part)
        except Exception as baseline_exc:
            logger.warning("倒扣标准对比失败（不影响入库）: %s", baseline_exc)

    # ---------- 汇总统计 ----------
    inserted_count = result.get("inserted_count", 0)
    updated_count = result.get("updated_count", 0)
    # 同一更新行可产生多条 metric（eCPM/收益各类型）+ 1 条 traffic，按位置去重后再与 updated_count 比较
    decrease_location_keys = {
        (
            str(item.get("date_str") or ""),
            str(item.get("product_name") or ""),
            str(item.get("country_code") or ""),
            str(item.get("ad_unit") or ""),
        )
        for item in (result.get("metric_decreases") or [])
    }
    decrease_location_keys.update(
        (
            str(item.get("date_str") or ""),
            str(item.get("product_name") or ""),
            str(item.get("country_code") or ""),
            str(item.get("ad_unit") or ""),
        )
        for item in (result.get("traffic_decreases") or [])
    )
    decrease_warning_count = len(decrease_location_keys)
    if decrease_warning_count > updated_count:
        logger.error(
            "数据减少告警数量异常: decrease_warnings=%d > updated_count=%d",
            decrease_warning_count,
            updated_count,
        )
    skipped_count = result.get("skipped_count", 0)
    zero_skipped_count = result.get("zero_skipped_count", 0)
    error_count = result.get("error_count", 0)
    assignment_gaps = result.get("assignment_gaps") or []
    assignment_orphan_total = int(result.get("assignment_orphan_total") or 0)
    country_unit_mismatches = result.get("country_unit_mismatches") or []
    country_unit_mismatch_total = int(result.get("country_unit_mismatch_total") or 0)
    report_type_line = format_report_type_counts_for_notify(
        result.get("report_type_counts")
    )

    result_summary = format_result_summary(
        inserted=inserted_count,
        updated=updated_count,
        skipped=skipped_count,
        error=error_count,
        zero_skipped=zero_skipped_count,
    )
    logger.info(f"数据导入完成: {result_summary}")

    # ---------- Telegram 通知（有写入时发送；分配空窗单独告警） ----------
    if inserted_count > 0 or updated_count > 0:
        params_block = format_notify_params_block(notify_params)
        telegram_msg = (
            f"⏰ {notify_title} 定时任务执行完成\n\n"
            f"执行时间: {current_time_str}\n"
            f"{params_block}"
        )
        if report_type_line:
            telegram_msg += f"报表类型: {report_type_line}\n"
        telegram_msg += (
            f"✅ 成功插入: {inserted_count} 条\n"
            f"✅ 成功更新: {updated_count} 条"
        )
        if skipped_count > 0:
            telegram_msg += f"\n⏭️ 跳过重复: {skipped_count} 条"
        if zero_skipped_count > 0:
            telegram_msg += f"\n⏭️ 跳过全零: {zero_skipped_count} 条"
        if error_count > 0:
            telegram_msg += f"\n❌ 错误: {error_count} 条"
        try:
            await send_telegram_notify_async(telegram_msg)
        except Exception as notify_err:
            logger.warning(f"发送 Telegram 通知失败: {task_name}: {notify_err}")

    if assignment_orphan_total > 0:
        gap_msg = format_assignment_gap_telegram_message(
            notify_title=notify_title,
            gaps=assignment_gaps,
            total_orphan=assignment_orphan_total,
        )
        try:
            await send_telegram_notify_async(gap_msg)
        except Exception as notify_err:
            logger.warning(f"发送产品分配空窗 Telegram 告警失败: {task_name}: {notify_err}")

    if country_unit_mismatch_total > 0:
        mismatch_msg = format_country_unit_mismatch_telegram_message(
            notify_title=notify_title,
            mismatches=country_unit_mismatches,
            total=country_unit_mismatch_total,
        )
        try:
            await send_telegram_notify_async(mismatch_msg)
        except Exception as notify_err:
            logger.warning(
                f"发送国家/广告单元同日收益不一致 Telegram 告警失败: "
                f"{task_name}: {notify_err}"
            )

    # ---------- 写入任务结果供调度器持久化 ----------
    if update_task_result:
        set_task_result(task_name, f"执行成功: {result_summary}")
    return result_summary


def preprocess_addermobi_match_counts(ad_data: List[Any]) -> List[Any]:
    """
    Addermobi 数据预处理：修正匹配广告请求数 + viewability_rate 单位对齐。

    1. 部分上游返回 MatchedAdRequests=0 但 AdRequestsCoverage 非零，
       此时按「请求数 × 覆盖率」推算匹配数，避免入库后指标异常。
    2. ActiveViewViewability 可能返回 0–1 小数（如 0.85=85%），
       平台 viewability_rate 为 0–100 百分比，需 ×100 对齐口径。
       与 AdRequestsCoverage 处理逻辑一致：值 > 1 视为百分比，值 ≤ 1 视为比例。

    参数:
        ad_data: API 原始行列表（就地修改 MatchedAdRequests / ActiveViewViewability）

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
                # AdRequestsCoverage 可能是 0–1 比例或 0–100 百分比
                rate = coverage_rate / 100.0 if coverage_rate > 1 else coverage_rate
                item["MatchedAdRequests"] = int(request_count * rate)

            # viewability_rate 单位对齐：0-1 小数 → 0-100 百分比
            viewability = item.get("ActiveViewViewability")
            if viewability is not None and viewability != "":
                try:
                    v_val = float(viewability)
                    if 0 < v_val <= 1:
                        item["ActiveViewViewability"] = v_val * 100
                except (ValueError, TypeError):
                    pass
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
    update_task_result: bool = True,
    notify_params: Optional[Mapping[str, Any]] = None,
    fetch_stats: Optional[Any] = None,
    data_source: str = "unknown",
    report_type: str = "legacy",
    upstream_account: str = "",
) -> str:
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
        notify_params: 可选任务参数，写入 Telegram 完成通知
        fetch_stats: 可选上游拉数分页统计，合并进 Telegram 通知
    """
    # ---------- 空数据快速返回 ----------
    if not data:
        logger.info("暂无产品数据")
        empty_msg = "执行成功: 暂无产品数据"
        if update_task_result:
            set_task_result(task_name, empty_msg)
        return empty_msg

    effective_notify_params = merge_notify_params_with_fetch_stats(
        notify_params,
        fetch_stats,
    )

    # ---------- 可选数据预处理 ----------
    if data_transform:
        data = data_transform(list(data))

    # ---------- 入库主流程 ----------
    async with AsyncSessionLocal() as db:
        # 广告数据处理需要关联管理员用户（审计/归属）
        admin_user = await get_admin_user(db)
        if not admin_user:
            logger.error("未找到管理员用户，无法处理产品，跳过本次任务")
            skip_msg = "跳过: 未找到管理员用户"
            if update_task_result:
                set_task_result(task_name, skip_msg)
            return skip_msg

        result = await process_api_ad_data(
            data=data,
            db=db,
            admin_user=admin_user,
            source=source,
            field_mapping=dict(field_mapping),
            data_source=data_source,
            report_type=report_type,
            upstream_account=upstream_account,
        )
        return await finalize_upstream_import(
            db,
            result,
            task_name=task_name,
            current_time_str=current_time_str,
            notify_title=notify_title,
            update_task_result=update_task_result,
            notify_params=effective_notify_params,
        )
