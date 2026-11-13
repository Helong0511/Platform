"""
FastAPI 应用 lifespan（启动 / 关闭）。
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect, text

from app.core.cache_manager import CacheManager
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine, init_db
from app.core.redis_client import close_redis_client, get_redis_client
from app.core.telegram.file_lock import is_lock_held as has_bot_lock
from app.core.telegram.file_lock import release_bot_lock
from app.core.telegram.polling_manager import start_bot_thread, stop_polling_application
from app.core.telegram.service_notify import (
    notify_service_started,
    notify_service_stopped,
    should_run_telegram_polling,
)
from app.core.telegram.shared_state import cleanup_stale_shared_state
from app.core.timezone_utils import check_and_validate_timezone, log_timezone_info
from app.db.migrations.gate import verify_schema_revision
from app.models import Base
from app.scheduler_module import init_scheduled_tasks, shutdown_scheduler, start_scheduler
from app.scheduler_module.task_init import init_scheduled_tasks_in_db

logger = logging.getLogger(__name__)


def _schema_metadata_drift(sync_connection, metadata=None) -> dict:
    """只读核验 ORM 表、列、类型、NULL、主键、索引、外键及显式表字符集规则；绝不执行 DDL。"""
    from sqlalchemy import Boolean, Integer, Numeric, String

    target_metadata = metadata or Base.metadata
    inspector = inspect(sync_connection)
    missing_tables = []
    missing_columns = {}
    column_type_mismatches = {}
    nullable_mismatches = {}
    primary_key_mismatches = {}
    index_mismatches = {}
    unique_constraint_mismatches = {}
    foreign_key_mismatches = {}
    check_constraint_mismatches = {}
    table_option_mismatches = {}

    def type_mismatch(expected_type, actual_type, dialect_name: str) -> bool:
        expected_affinity = expected_type._type_affinity
        actual_affinity = actual_type._type_affinity
        if dialect_name == "mysql" and isinstance(expected_type, Boolean):
            is_mysql_boolean_storage = (
                actual_type.__class__.__name__.upper() == "TINYINT"
                and (
                    getattr(actual_type, "display_width", None) == 1
                    or getattr(actual_type, "length", None) == 1
                )
            )
            affinity_matches = actual_affinity is Boolean or is_mysql_boolean_storage
        else:
            affinity_matches = expected_affinity is actual_affinity
        if not affinity_matches:
            return True
        if isinstance(expected_type, String) and expected_type.length is not None:
            if getattr(actual_type, "length", None) != expected_type.length:
                return True
        if isinstance(expected_type, Numeric):
            for attribute in ("precision", "scale"):
                expected_value = getattr(expected_type, attribute, None)
                if expected_value is not None and getattr(actual_type, attribute, None) != expected_value:
                    return True
        expected_collation = getattr(expected_type, "collation", None)
        if expected_collation and getattr(actual_type, "collation", None) != expected_collation:
            return True
        return False

    def foreign_key_signature(item):
        options = item.get("options") or {}
        return (
            tuple(item.get("constrained_columns") or ()),
            item.get("referred_table"),
            tuple(item.get("referred_columns") or ()),
            (options.get("ondelete") or "").upper(),
            (options.get("onupdate") or "").upper(),
        )

    dialect_name = sync_connection.dialect.name
    for table in target_metadata.sorted_tables:
        if not inspector.has_table(table.name, schema=table.schema):
            missing_tables.append(table.fullname)
            continue

        actual_columns = {
            column["name"]: column
            for column in inspector.get_columns(table.name, schema=table.schema)
        }
        absent = sorted(
            column.name for column in table.columns
            if column.name not in actual_columns
        )
        if absent:
            missing_columns[table.fullname] = absent

        for column in table.columns:
            actual = actual_columns.get(column.name)
            if actual is None:
                continue
            if type_mismatch(column.type, actual["type"], dialect_name):
                column_type_mismatches.setdefault(table.fullname, {})[column.name] = {
                    "expected": str(column.type),
                    "actual": str(actual["type"]),
                }
            # 主键列的非空语义由 PK 约束保证；SQLite 反射可能报告 nullable=True。
            if (
                not column.primary_key
                and bool(actual["nullable"]) != bool(column.nullable)
            ):
                nullable_mismatches.setdefault(table.fullname, {})[column.name] = {
                    "expected": bool(column.nullable),
                    "actual": bool(actual["nullable"]),
                }

        expected_pk = sorted(column.name for column in table.primary_key.columns)
        actual_pk = sorted(
            inspector.get_pk_constraint(table.name, schema=table.schema).get("constrained_columns") or []
        )
        if expected_pk != actual_pk:
            primary_key_mismatches[table.fullname] = {
                "expected": expected_pk,
                "actual": actual_pk,
            }

        expected_indexes = sorted(
            (index.name, tuple(column.name for column in index.columns))
            for index in table.indexes
            if not index.unique
        )
        actual_indexes = sorted(
            (item.get("name"), tuple(item.get("column_names") or ()))
            for item in inspector.get_indexes(table.name, schema=table.schema)
            if item.get("name") and not item.get("unique")
        )
        if expected_indexes != actual_indexes:
            index_mismatches[table.fullname] = {
                "expected": expected_indexes,
                "actual": actual_indexes,
            }

        expected_unique = sorted({
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        } | {
            tuple(column.name for column in index.columns)
            for index in table.indexes
            if index.unique
        })
        actual_unique = sorted({
            tuple(item.get("column_names") or ())
            for item in inspector.get_unique_constraints(table.name, schema=table.schema)
        } | {
            tuple(item.get("column_names") or ())
            for item in inspector.get_indexes(table.name, schema=table.schema)
            if item.get("unique")
        })
        if expected_unique != actual_unique:
            unique_constraint_mismatches[table.fullname] = {
                "expected": expected_unique,
                "actual": actual_unique,
            }

        expected_fks = sorted(
            (
                tuple(element.parent.name for element in fk.elements),
                fk.elements[0].column.table.name,
                tuple(element.column.name for element in fk.elements),
                (fk.ondelete or "").upper(),
                (fk.onupdate or "").upper(),
            )
            for fk in table.foreign_key_constraints
        )
        actual_fks = sorted(
            foreign_key_signature(item)
            for item in inspector.get_foreign_keys(table.name, schema=table.schema)
        )
        if expected_fks != actual_fks:
            foreign_key_mismatches[table.fullname] = {
                "expected": expected_fks,
                "actual": actual_fks,
            }

        # CHECK 约束属于数据库完整性边界；名称由 ORM 与版本化 migration 共同维护。
        expected_checks = sorted(
            constraint.name
            for constraint in table.constraints
            if constraint.__class__.__name__ == "CheckConstraint" and constraint.name
        )
        actual_checks = sorted(
            item.get("name")
            for item in inspector.get_check_constraints(table.name, schema=table.schema)
            if item.get("name")
        )
        if expected_checks != actual_checks:
            check_constraint_mismatches[table.fullname] = {
                "expected": expected_checks,
                "actual": actual_checks,
            }

        if dialect_name == "mysql":
            expected_options = {}
            mysql_options = table.dialect_options["mysql"]
            for option, inspector_key in (
                ("charset", "mysql_charset"),
                ("collate", "mysql_collate"),
            ):
                expected_value = mysql_options.get(option)
                if expected_value:
                    expected_options[inspector_key] = expected_value
            if expected_options:
                # MySQL Inspector.get_table_options() 在部分驱动版本中不返回 charset/collation；
                # 从 information_schema 读取服务器实际记录，不能把 None 当作真实值。
                schema_name = table.schema or sync_connection.execute(
                    text("SELECT DATABASE()")
                ).scalar_one_or_none()
                actual_collation = None
                actual_charset = None
                if schema_name:
                    actual_collation = sync_connection.execute(
                        text(
                            "SELECT TABLE_COLLATION FROM information_schema.TABLES "
                            "WHERE TABLE_SCHEMA = :schema_name AND TABLE_NAME = :table_name"
                        ),
                        {"schema_name": schema_name, "table_name": table.name},
                    ).scalar_one_or_none()
                    if actual_collation:
                        actual_charset = sync_connection.execute(
                            text(
                                "SELECT CHARACTER_SET_NAME FROM information_schema.COLLATIONS "
                                "WHERE COLLATION_NAME = :collation_name"
                            ),
                            {"collation_name": actual_collation},
                        ).scalar_one_or_none()
                actual_options = {
                    "mysql_charset": actual_charset,
                    "mysql_collate": actual_collation,
                }
                mismatches = {
                    key: {
                        "expected": value,
                        "actual": actual_options.get(key),
                    }
                    for key, value in expected_options.items()
                    if (actual_options.get(key) or "").lower() != value.lower()
                }
                if mismatches:
                    table_option_mismatches[table.fullname] = mismatches

    return {
        "missing_tables": sorted(missing_tables),
        "missing_columns": missing_columns,
        "column_type_mismatches": column_type_mismatches,
        "nullable_mismatches": nullable_mismatches,
        "primary_key_mismatches": primary_key_mismatches,
        "index_mismatches": index_mismatches,
        "unique_constraint_mismatches": unique_constraint_mismatches,
        "foreign_key_mismatches": foreign_key_mismatches,
        "check_constraint_mismatches": check_constraint_mismatches,
        "table_option_mismatches": table_option_mismatches,
    }


async def _verify_database_schema() -> str | None:
    """只读核验 migration revision 与 ORM 表/列/类型/NULL/主键/索引/外键/显式字符集；应用 Worker 不执行 schema DDL。"""
    async with engine.connect() as connection:
        current_revision = await verify_schema_revision(connection)
        drift = await connection.run_sync(_schema_metadata_drift)
        if any(drift.values()):
            raise RuntimeError(
                "数据库 schema 与 ORM 不一致："
                f"missing_tables={drift['missing_tables']}; "
                f"missing_columns={drift['missing_columns']}; "
                f"column_type_mismatches={drift['column_type_mismatches']}; "
                f"nullable_mismatches={drift['nullable_mismatches']}; "
                f"primary_key_mismatches={drift['primary_key_mismatches']}; "
                f"index_mismatches={drift['index_mismatches']}; "
                f"unique_constraint_mismatches={drift['unique_constraint_mismatches']}; "
                f"foreign_key_mismatches={drift['foreign_key_mismatches']}; "
                f"check_constraint_mismatches={drift['check_constraint_mismatches']}; "
                f"table_option_mismatches={drift['table_option_mismatches']}"
            )
    return current_revision


async def _sync_scheduled_tasks_for_worker(worker_pid: int) -> None:
    """同步任务配置；调度 Worker 同步失败时拒绝启动，纯 API Worker 可降级。"""
    try:
        await init_scheduled_tasks_in_db()
        logger.info("[Worker PID:%s] 定时任务配置已同步到数据库", worker_pid)
    except Exception as db_init_error:
        # 不输出数据库异常原文，避免日志泄露 SQL 参数。
        logger.error(
            "[Worker PID:%s] 定时任务配置同步失败：exception_type=%s",
            worker_pid,
            type(db_init_error).__name__,
        )
        # 纯 API Worker（未运行 APScheduler）可降级启动；调度 Worker 不能使用旧配置继续调度。
        if settings.should_run_scheduler():
            raise RuntimeError(
                "定时任务配置同步失败，调度 Worker 拒绝启动"
            ) from db_init_error


async def _start_scheduler_for_worker(worker_pid: int) -> None:
    """启动 APScheduler；任何初始化失败都必须阻止调度 Worker 就绪。"""
    try:
        logger.info("[Worker PID:%s] 开始初始化定时任务调度器...", worker_pid)
        await init_scheduled_tasks()
        logger.info("[Worker PID:%s] 定时任务初始化完成，正在启动调度器...", worker_pid)
        await start_scheduler()
        logger.info("[Worker PID:%s] 定时任务调度器已启动", worker_pid)
    except Exception as scheduler_error:
        # 调度器不可用时不能将 Worker 标记为健康；日志不输出异常原文。
        logger.error(
            "[Worker PID:%s] 定时任务调度器启动失败：exception_type=%s",
            worker_pid,
            type(scheduler_error).__name__,
        )
        raise RuntimeError("定时任务调度器启动失败，调度 Worker 拒绝就绪") from scheduler_error


def _should_run_cache_warmup() -> bool:
    """仅在单进程或 Gunicorn 的首个 API worker 中执行预热。"""
    if os.getenv("GUNICORN_ROLE", "api").strip().lower() == "scheduler":
        return False
    worker_marker = os.getenv("SCHEDULER_WORKER", "").strip()
    if worker_marker:
        return worker_marker == "1"
    return True


# ====== 应用生命周期管理 ======
# 使用 lifespan 上下文管理器替代已弃用的 @app.on_event()
# 这是 FastAPI 0.95.0+ 推荐的方式，提供更好的资源管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理（启动 / 关闭）。

    启动：时区校验 → 只读 schema revision/drift gate → init_db → 缓存预热 → 调度器与 Telegram Bot → Redis
    关闭：停止调度器、释放 Bot 锁、关闭 Redis、通知服务下线
    """
    # ====== 启动时执行 ======
    worker_pid = os.getpid()
    redis_client = None
    cache_warmup_task = None
    logger.info(f"[Worker PID:{worker_pid}] 应用启动中...")

    # 检查并验证时区配置（启动时首先检查）
    try:
        timezone_consistent = check_and_validate_timezone()
        if not timezone_consistent:
            logger.warning(
                f"[Worker PID:{worker_pid}] 系统时区与配置时区不一致，"
                "应用将使用配置的时区处理所有时间操作"
            )
        # 记录详细的时区信息
        log_timezone_info()
    except Exception as e:
        logger.warning(f"时区检查时出错: {e}，继续启动...")

    try:
        from app.core.tracking.click_persist import log_click_persist_mode_at_startup

        log_click_persist_mode_at_startup()
    except Exception as e:
        logger.debug("点击落库策略日志跳过: %s", e)

    # 只读核验数据库 migration revision 与 ORM 结构；API/Scheduler Worker 不创建数据库或执行 DDL。
    # 新库必须先由 provisioning 导入基线并运行独立 Migration Runner。
    try:
        current_revision = await _verify_database_schema()
        logger.info(
            "[Worker PID:%s] 数据库 schema revision 与 ORM 结构核验通过：revision=%s",
            worker_pid,
            current_revision,
        )
    except Exception as exc:
        logger.error(
            "[Worker PID:%s] 数据库 schema 初始化/核验失败，拒绝启动：exception_type=%s",
            worker_pid,
            type(exc).__name__,
        )
        raise RuntimeError("数据库 schema 未达到应用启动要求，拒绝启动") from exc

    # 初始化数据库，创建默认管理员账户；核心 DB 初始化失败时不得继续对外提供服务。
    try:
        await init_db()
        logger.info(f"[Worker PID:{worker_pid}] 数据库初始化完成（包括默认管理员账户）")
    except Exception as exc:
        logger.error(
            "[Worker PID:%s] 数据库初始化失败，拒绝启动：exception_type=%s",
            worker_pid,
            type(exc).__name__,
        )
        raise RuntimeError("数据库初始化失败，拒绝启动") from exc

    # 加载标准维度配置（scheduled_tasks.standard_report_type → 内存）
    try:
        from app.core.ad_data_metadata import refresh_standard_report_types
        await refresh_standard_report_types()
        logger.info(f"[Worker PID:{worker_pid}] 标准维度配置加载完成")
    except Exception as e:
        logger.warning(f"[Worker PID:{worker_pid}] 标准维度配置加载失败: {e}，使用内置默认值")

    # 初始化Redis连接（如果配置了）
    try:
        redis_client = await get_redis_client()
        if redis_client:
            logger.info(f"[Worker PID:{worker_pid}] Redis连接已初始化")
        else:
            logger.info(
                f"[Worker PID:{worker_pid}] Redis不可用；支持降级的组件使用内存存储，"
                "短链接/Offer缓存与预热已禁用"
            )
    except Exception as e:
        logger.warning(
            f"[Worker PID:{worker_pid}] Redis初始化失败: {e}；"
            "支持降级的组件使用内存存储，短链接/Offer缓存与预热已禁用"
        )

    # 同步 task_config.py → scheduled_tasks 表；调度 Worker 必须依赖完整配置。
    await _sync_scheduled_tasks_for_worker(worker_pid)

    # 定时任务调度器：仅调度 worker 启动（Gunicorn 多 worker 时由 SCHEDULER_WORKER=1 标识）
    if settings.should_run_scheduler():
        await _start_scheduler_for_worker(worker_pid)
    else:
        logger.info(
            f"[Worker PID:{worker_pid}] 跳过定时任务调度器"
            f"（ENABLE_SCHEDULER/SCHEDULER_WORKER 未启用本 worker；任务记录已同步到数据库）"
        )

    # Telegram：调度进程只发启停通知；API 进程才启动 Bot 轮询（单实例文件锁）
    try:
        cleanup_stale_shared_state()
        telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
        logger.info(
            f"[Worker PID:{worker_pid}] Telegram 启用={telegram_enabled}, "
            f"轮询={should_run_telegram_polling()}"
        )
        if not telegram_enabled:
            logger.info(f"[Worker PID:{worker_pid}] Telegram 已禁用，跳过")
        elif should_run_telegram_polling():
            from app.core.telegram.bot_initializer import initialize_bot
            from app.core.telegram import bot_state

            logger.info(f"[Worker PID:{worker_pid}] 初始化 Telegram Bot（API 进程）...")
            bot_instance, initialized, available = initialize_bot()
            logger.info(
                f"[Worker PID:{worker_pid}] Bot 初始化: initialized={initialized}, available={available}"
            )
            bot_initialized = bot_state.bot_initialized

            if initialized and bot_initialized:
                start_success = start_bot_thread()
                if not start_success:
                    logger.info(
                        f"[Worker PID:{worker_pid}] Bot 轮询未启动（其他进程已占用或未取得锁）"
                    )
            else:
                logger.info(f"[Worker PID:{worker_pid}] Bot 未配置或初始化失败，跳过轮询")
        else:
            logger.info(
                f"[Worker PID:{worker_pid}] 调度进程不启动 Bot 轮询，仅发送服务启停通知"
            )
    except Exception as e:
        logger.error(f"[Worker PID:{worker_pid}] Telegram 初始化失败: {e}", exc_info=True)
        logger.warning(f"[Worker PID:{worker_pid}] 应用将继续启动，Telegram 可能不可用")

    # 缓存预热：Redis 可用时，仅由首个 API worker 后台执行
    if redis_client and _should_run_cache_warmup():
        # 在后台任务中执行缓存预热，不阻塞应用启动
        async def warmup_cache_background():
            """启动后后台预热字典/配置类缓存，失败仅打警告不阻塞服务。"""
            try:
                async with AsyncSessionLocal() as db:
                    await CacheManager.warmup_all(db)
            except Exception as e:
                logger.warning(f"缓存预热失败: {e}，不影响应用启动")

        # 延迟执行缓存预热，确保数据库和Redis都已初始化
        cache_warmup_task = asyncio.create_task(warmup_cache_background())
        logger.info(f"[Worker PID:{worker_pid}] 缓存预热任务已启动（后台执行）")
    elif not redis_client:
        logger.info(f"[Worker PID:{worker_pid}] 跳过缓存预热：Redis 不可用")
    else:
        logger.info(f"[Worker PID:{worker_pid}] 跳过缓存预热：由首个 API worker 执行")

    # 启动系统监控与性能优化后台任务
    try:
        from app.core.monitoring import start_monitoring_tasks
        from app.core.performance_optimization import (
            optimization_manager,
            start_bottleneck_detection,
        )

        await optimization_manager.ensure_hydrated_from_redis()
        asyncio.create_task(start_monitoring_tasks())
        asyncio.create_task(start_bottleneck_detection())
        logger.info(f"[Worker PID:{worker_pid}] 系统监控与瓶颈检测任务已启动")
    except Exception as e:
        logger.error(f"[Worker PID:{worker_pid}] 系统监控/瓶颈检测任务启动失败: {e}", exc_info=True)
        logger.warning(f"[Worker PID:{worker_pid}] 应用将继续启动，监控功能可能不可用")

    logger.info("应用启动完成")

    # 启动通知放到后台，避免 Telegram 不可达时在 yield 前阻塞、延迟 API 监听
    if getattr(settings, "TELEGRAM_ENABLE", True):

        async def _send_startup_notify_background() -> None:
            try:
                sent = await asyncio.to_thread(notify_service_started)
                if sent:
                    logger.info(f"[Worker PID:{worker_pid}] 已发送服务启动 Telegram 通知")
                else:
                    logger.debug(
                        f"[Worker PID:{worker_pid}] 未发送服务启动通知（非通知 worker 或已禁用）"
                    )
            except Exception as e:
                logger.warning(f"发送服务启动通知失败: {e}", exc_info=True)

        asyncio.create_task(_send_startup_notify_background())
    else:
        logger.info(f"[Worker PID:{worker_pid}] TELEGRAM_ENABLE=false，跳过服务启动通知")

    # ====== 应用运行期间 ======
    yield

    # ====== 关闭时执行 ======
    logger.info("应用关闭中...")
    if cache_warmup_task and not cache_warmup_task.done():
        cache_warmup_task.cancel()
        try:
            await cache_warmup_task
        except asyncio.CancelledError:
            logger.debug("缓存预热任务已取消")
    try:
        from app.core.monitoring import system_monitor

        await system_monitor.stop_resource_monitor()
    except asyncio.CancelledError:
        logger.debug("资源监控关闭时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭资源监控时出现错误: {e}")
    try:
        from app.scheduler_module.scheduler import mark_scheduler_shutting_down

        mark_scheduler_shutting_down()
    except Exception:
        pass
    try:
        if settings.should_run_scheduler():
            await shutdown_scheduler()
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("定时任务调度器关闭时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭定时任务调度器时出现错误: {e}")

    try:
        # 关闭Redis连接
        await close_redis_client()
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("Redis连接关闭时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭Redis连接时出现错误: {e}")

    try:
        telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
        if telegram_enabled:
            try:
                notify_service_stopped()
            except asyncio.CancelledError:
                logger.debug("发送服务关闭通知时任务被取消（正常关闭流程）")
            except asyncio.TimeoutError:
                logger.debug("发送服务关闭通知超时（可能连接已断开）")
            from app.core.telegram import bot_state as _bot_state_mod
            if (
                should_run_telegram_polling()
                and _bot_state_mod.bot_initialized
                and has_bot_lock()
            ):
                try:
                    stop_polling_application(timeout=8.0)
                except Exception as stop_err:
                    logger.warning(f"停止 Telegram Application 时出错: {stop_err}")
                try:
                    release_bot_lock()
                except Exception as stop_err:
                    logger.warning(f"释放 Telegram Bot 锁时出错: {stop_err}")
            elif should_run_telegram_polling() and _bot_state_mod.bot_initialized:
                logger.debug(f"[PID:{os.getpid()}] 未持有 Bot 锁，跳过 stop_bot")
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("关闭 Telegram 机器人时任务被取消（正常关闭流程）")
    except Exception as e:
        logger.warning(f"关闭 Telegram 机器人时出现错误: {e}")

    try:
        # 清理数据库连接池
        await engine.dispose()
        logger.info("数据库连接池已关闭")
    except asyncio.CancelledError:
        # 应用关闭时任务被取消是正常的，不需要记录错误
        logger.debug("关闭数据库连接池时任务被取消（正常关闭流程）")
    except Exception as e:
        # 关闭时的错误不应该影响应用关闭流程
        logger.warning(f"关闭数据库连接池时出现错误: {e}")
    finally:
        logger.info("应用已关闭")
        # 排空异步日志队列，减少优雅关闭时尾部日志丢失
        try:
            from app.core.log_queue import shutdown_log_queue

            shutdown_log_queue(timeout_sec=2.0)
        except Exception:
            pass
