"""
FastAPI 应用 lifespan（启动 / 关闭）。
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
from app.models import Base
from app.scheduler_module import init_scheduled_tasks, shutdown_scheduler, start_scheduler
from app.scheduler_module.task_init import init_scheduled_tasks_in_db

logger = logging.getLogger(__name__)


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

    启动：时区校验 → 建表 → init_db → 缓存预热 → 调度器与 Telegram Bot → Redis
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

    # 确保数据库存在并创建表（多进程环境：每个 worker 都会执行，但数据库操作是安全的）
    try:
        from app.db.database import create_database

        # 创建数据库（如果不存在）
        await create_database()

        # 创建所有表（如果不存在，使用 IF NOT EXISTS 语义）
        # 导入所有模型以确保SQLAlchemy能够发现所有表
        from app.models import (
            User, Client, Product, AdData, ProductAssignment,
            ScheduledTask, UserAuditLog, UserSession, TokenBlacklist,
            PostbackConversion, PendingPostbackConversion, PostbackIpWhitelist
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info(f"[Worker PID:{worker_pid}] 数据库表创建完成")
    except Exception as e:
        # 检查是否是 MySQL 并发 DDL 错误（错误代码 1684）
        # 这个错误表示表正在被其他进程修改，可以安全忽略
        is_concurrent_ddl_error = False
        error_code = None

        # 尝试从异常中提取错误代码
        try:
            if hasattr(e, 'orig'):
                # SQLAlchemy 包装的异常 (sqlalchemy.exc.OperationalError)
                orig = e.orig
                if hasattr(orig, 'args') and len(orig.args) > 0:
                    error_code = orig.args[0] if isinstance(orig.args[0], int) else None
            elif hasattr(e, 'args') and len(e.args) > 0:
                # 直接 pymysql 异常
                error_code = e.args[0] if isinstance(e.args[0], int) else None

            # 检查错误代码或错误消息
            if error_code == 1684 or (str(e) and '1684' in str(e)):
                is_concurrent_ddl_error = True
        except Exception:
            # 如果提取错误代码失败，检查错误消息
            error_str = str(e)
            if '1684' in error_str or 'concurrent DDL' in error_str.lower():
                is_concurrent_ddl_error = True

        if is_concurrent_ddl_error:
            # 这是预期的并发行为，降级为信息级别
            logger.info(
                f"[Worker PID:{worker_pid}] 检测到并发 DDL 操作（表可能正在被其他 worker 创建），"
                f"这是正常的多进程环境行为，继续启动..."
            )
        else:
            # 其他错误，记录为错误级别
            logger.error(f"[Worker PID:{worker_pid}] 数据库表创建失败: {e}", exc_info=True)
            # 不抛出异常，允许应用继续启动（可能是表已存在或其他 worker 已创建）
            logger.warning(f"[Worker PID:{worker_pid}] 继续启动应用...")

    # 初始化数据库，创建默认管理员账户
    try:
        await init_db()
        logger.info(f"[Worker PID:{worker_pid}] 数据库初始化完成（包括默认管理员账户）")
    except Exception as e:
        logger.error(f"[Worker PID:{worker_pid}] 数据库初始化失败: {e}", exc_info=True)
        # 不抛出异常，允许应用继续启动

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

    # 同步 task_config.py → scheduled_tasks 表（与是否启动 APScheduler 解耦）
    # 本地 Windows 常见 ENABLE_SCHEDULER=false 仅跑 API，仍须写入新任务供管理端展示与后续启用调度
    try:
        await init_scheduled_tasks_in_db()
        logger.info(f"[Worker PID:{worker_pid}] 定时任务配置已同步到数据库")
    except Exception as db_init_error:
        logger.warning(
            f"[Worker PID:{worker_pid}] 同步任务到数据库失败: {db_init_error}，继续启动..."
        )

    # 定时任务调度器：仅调度 worker 启动（Gunicorn 多 worker 时由 SCHEDULER_WORKER=1 标识）
    if settings.should_run_scheduler():
        try:
            logger.info(f"[Worker PID:{worker_pid}] 开始初始化定时任务调度器...")

            await init_scheduled_tasks()
            logger.info(f"[Worker PID:{worker_pid}] 定时任务初始化完成，正在启动调度器...")
            await start_scheduler()
            logger.info(f"[Worker PID:{worker_pid}] 定时任务调度器已启动")
        except Exception as e:
            logger.error(f"[Worker PID:{worker_pid}] 定时任务初始化失败: {e}", exc_info=True)
            logger.warning(f"[Worker PID:{worker_pid}] 应用将继续启动，但定时任务功能可能不可用")
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
