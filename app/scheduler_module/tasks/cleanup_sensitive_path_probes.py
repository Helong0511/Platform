"""
敏感路径探测日志有界分批清理任务。
每批按主键稳定排序、有限行锁和独立事务提交；预算耗尽明确返回未完成状态。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.models.models import SensitivePathProbeLog
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.scheduler_module.task_utils import log_task_error, log_task_start

logger = logging.getLogger(__name__)
TASK_NAME = "清理敏感路径拦截日志"

DEFAULT_BATCH_SIZE = 500
MAX_BATCH_SIZE = 5000
DEFAULT_MAX_BATCHES = 20
MAX_BATCHES_LIMIT = 1000
DEFAULT_MAX_RUNTIME_SECONDS = 20
MAX_RUNTIME_SECONDS_LIMIT = 300


class SensitivePathProbeCleanupError(RuntimeError):
    """清理失败；携带已提交批次的真实进度，不包含数据库异常原文。"""

    def __init__(self, *, deleted_count: int, batch_count: int, cutoff: str, error_type: str):
        self.deleted_count = deleted_count
        self.batch_count = batch_count
        self.cutoff = cutoff
        self.complete = False
        self.remaining_possible = True
        self.error_type = error_type
        super().__init__(
            f"敏感路径日志分批清理失败（{error_type}）；"
            f"已提交删除 {deleted_count} 条，完成 {batch_count} 批，尚可能有剩余数据"
        )



class SensitivePathProbeCleanupIncomplete(RuntimeError):
    """单轮预算耗尽；用于让调度器将部分清理记录为未完成而非成功。"""

    def __init__(self, result: dict):
        self.deleted_count = int(result["deleted_count"])
        self.batch_count = int(result["batch_count"])
        self.cutoff = str(result["cutoff"])
        self.complete = False
        self.remaining_possible = bool(result["remaining_possible"])
        super().__init__(
            f"敏感路径日志清理未完成：已提交删除 {self.deleted_count} 条，"
            f"完成 {self.batch_count} 批；剩余数据将在后续计划任务处理"
        )


def _positive_int(name: str, value: Any, *, maximum: int) -> int:
    """严格验证整数配置，拒绝 bool、隐式转换和超出硬上限的值。"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > maximum:
        raise ValueError(f"{name} 必须是 1 到 {maximum} 之间的整数")
    return value


async def cleanup_sensitive_path_probe_logs(
    retention_days: int | None = None,
    db: AsyncSession | None = None,
    *,
    batch_size: int | None = None,
    max_batches: int | None = None,
    max_runtime_seconds: int | None = None,
) -> dict:
    """
    按固定 cutoff 分批清理过期日志。

    每批先按 id 升序锁定最多 batch_size 个过期主键，再按主键和 cutoff 删除，
    每批独立 commit。传入 db 时由调用方管理会话生命周期，但本函数会像旧实现
    一样提交事务（现在每批提交一次）；调用方不得在传入前放置需要原子提交的其它写入。

    complete=False 表示达到批次或运行预算，remaining_possible=True。
    批次失败抛出 SensitivePathProbeCleanupError，异常属性保留此前已提交的进度。
    """
    raw_days = settings.SENSITIVE_PATH_PROBE_RETENTION_DAYS if retention_days is None else retention_days
    days = _positive_int("retention_days", raw_days, maximum=36500)
    raw_batch_size = (
        getattr(settings, "SENSITIVE_PATH_PROBE_CLEANUP_BATCH_SIZE", DEFAULT_BATCH_SIZE)
        if batch_size is None else batch_size
    )
    raw_max_batches = (
        getattr(settings, "SENSITIVE_PATH_PROBE_CLEANUP_MAX_BATCHES", DEFAULT_MAX_BATCHES)
        if max_batches is None else max_batches
    )
    raw_runtime = (
        getattr(settings, "SENSITIVE_PATH_PROBE_CLEANUP_MAX_RUNTIME_SECONDS", DEFAULT_MAX_RUNTIME_SECONDS)
        if max_runtime_seconds is None else max_runtime_seconds
    )
    batch_size = _positive_int("batch_size", raw_batch_size, maximum=MAX_BATCH_SIZE)
    max_batches = _positive_int("max_batches", raw_max_batches, maximum=MAX_BATCHES_LIMIT)
    max_runtime_seconds = _positive_int(
        "max_runtime_seconds", raw_runtime, maximum=MAX_RUNTIME_SECONDS_LIMIT
    )

    # 全部批次复用同一应用时间快照，边界不会随任务运行时间漂移。
    cutoff_dt = get_app_now_naive() - timedelta(days=days)
    cutoff = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
    started = time.monotonic()
    log_task_start(
        TASK_NAME,
        f"开始分批清理 {days} 天前日志（<{cutoff}），每批最多 {batch_size} 条，"
        f"最多 {max_batches} 批，运行预算 {max_runtime_seconds} 秒",
    )

    use_external_db = db is not None
    if not use_external_db:
        db = AsyncSessionLocal()

    deleted_count = 0
    batch_count = 0
    complete = False
    try:
        while batch_count < max_batches:
            if time.monotonic() - started >= max_runtime_seconds:
                break

            # 使用锁定读而不使用 SKIP LOCKED：空结果才能证明没有剩余过期行。
            # 并发清理实例可等待当前批次提交；wait_for 会限制锁等待时间。
            # SQLite 方言会忽略 FOR UPDATE，仅用于逻辑单测，不替代 MySQL 集成验证。
            async def _commit_one_batch() -> int | None:
                selected = await db.execute(
                    select(SensitivePathProbeLog.id)
                    .where(SensitivePathProbeLog.created_at < cutoff_dt)
                    .order_by(SensitivePathProbeLog.id.asc())
                    .limit(batch_size)
                    .with_for_update()
                )
                ids = list(selected.scalars().all())
                if not ids:
                    return None

                result = await db.execute(
                    delete(SensitivePathProbeLog).where(
                        SensitivePathProbeLog.id.in_(ids),
                        SensitivePathProbeLog.created_at < cutoff_dt,
                    )
                )
                batch_deleted = max(0, int(result.rowcount or 0))
                await db.commit()
                return batch_deleted

            # 单批查询、删除和提交共享剩余运行预算；避免慢 SQL/锁等待突破总时限。
            remaining_budget = max_runtime_seconds - (time.monotonic() - started)
            if remaining_budget <= 0:
                break
            batch_deleted = await asyncio.wait_for(
                _commit_one_batch(),
                timeout=remaining_budget,
            )
            if batch_deleted is None:
                complete = True
                break
            deleted_count += batch_deleted
            batch_count += 1

            logger.info(
                "敏感路径日志清理批次已提交: batch=%s deleted=%s total_deleted=%s",
                batch_count, batch_deleted, deleted_count,
            )

        elapsed = max(0.0, time.monotonic() - started)
        result_data = {
            "deleted_count": deleted_count,
            "batch_count": batch_count,
            "complete": complete,
            "remaining_possible": not complete,
            "retention_days": days,
            "cutoff": cutoff,
            "elapsed_seconds": round(elapsed, 3),
            "batch_size": batch_size,
            "max_batches": max_batches,
            "max_runtime_seconds": max_runtime_seconds,
        }
        if complete:
            msg = f"清理完成：删除 {deleted_count} 条，执行 {batch_count} 批，保留最近 {days} 天"
            logger.info("%s 执行完成: %s", TASK_NAME, msg)
            set_task_result(TASK_NAME, msg)
        else:
            msg = (
                f"清理未完成：已提交删除 {deleted_count} 条，执行 {batch_count} 批；"
                "已达到本轮批次或运行预算，仍可能存在待清理数据"
            )
            logger.warning("[定时任务未完成] %s: %s", TASK_NAME, msg)
            set_task_result(TASK_NAME, msg)
        return {**result_data, "message": msg}

    except Exception as exc:
        error_type = type(exc).__name__
        try:
            await db.rollback()
        except Exception as rollback_exc:
            logger.error("敏感路径日志清理回滚失败: error_type=%s", type(rollback_exc).__name__)
        err = SensitivePathProbeCleanupError(
            deleted_count=deleted_count,
            batch_count=batch_count,
            cutoff=cutoff,
            error_type=error_type,
        )
        log_task_error(
            TASK_NAME,
            f"清理失败（{error_type}）；已提交删除 {deleted_count} 条，完成 {batch_count} 批",
            exc_info=False,
        )
        set_task_result(TASK_NAME, f"清理失败（{error_type}）；已提交删除 {deleted_count} 条")
        # 不保留原始异常链，避免驱动异常中的 SQL/DSN/凭据进入调度器异常日志。
        raise err from None
    finally:
        if not use_external_db:
            await db.close()


async def cleanup_sensitive_path_probe_logs_task(**kwargs) -> dict:
    """正式调度入口：将配置/执行失败及预算耗尽的部分清理明确报告给调度器。"""
    try:
        result = await cleanup_sensitive_path_probe_logs(**kwargs)
    except SensitivePathProbeCleanupError:
        raise
    except Exception as exc:
        # 配置校验、会话创建等发生在批次事务之前，也必须覆盖旧的成功状态。
        set_task_result(TASK_NAME, f"清理失败（{type(exc).__name__}）")
        raise
    if not result["complete"]:
        raise SensitivePathProbeCleanupIncomplete(result)
    return result


__all__ = [
    "SensitivePathProbeCleanupError",
    "SensitivePathProbeCleanupIncomplete",
    "cleanup_sensitive_path_probe_logs",
    "cleanup_sensitive_path_probe_logs_task",
    "get_task_result",
]
