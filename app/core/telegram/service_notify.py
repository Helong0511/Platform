"""
按 Gunicorn 角色（Platform-backend / Platform-scheduler）发送服务启停 Telegram 通知。
与 Bot 轮询锁无关，使用 HTTP 发消息即可。
"""
import logging
import os

from app.core.config import settings
from app.core.telegram.message_sender import send_telegram_message

logger = logging.getLogger(__name__)


def get_gunicorn_role() -> str:
    """读取 Gunicorn 进程角色：api（默认）或 scheduler。"""
    return os.getenv("GUNICORN_ROLE", "api").strip().lower()


def get_service_display_name() -> str:
    """systemd 服务对应的展示名称。"""
    if get_gunicorn_role() == "scheduler":
        return "Platform Scheduler（定时任务）"
    return "Platform Backend（API）"


def get_service_port_hint() -> str:
    """返回当前服务对外监听端口提示（scheduler 8961，api 8960）。"""
    if get_gunicorn_role() == "scheduler":
        return "8961"
    return "8960"


def should_run_telegram_polling() -> bool:
    """仅 API 进程启动 Bot 长轮询；调度进程只发启停通知，避免双实例抢锁。"""
    return get_gunicorn_role() != "scheduler"


def should_send_service_lifecycle_notify() -> bool:
    """
    每个实例只由一个 worker 发送启停通知，避免重复刷屏。

    - scheduler：仅 1 个 worker，始终发送
    - api + Gunicorn：仅 post_fork 标记的 SCHEDULER_WORKER=1 发送
    - 未设置 SCHEDULER_WORKER：本地 uvicorn / 单进程启动，应发送
    """
    if get_gunicorn_role() == "scheduler":
        return True
    scheduler_worker = os.getenv("SCHEDULER_WORKER", "").strip()
    if scheduler_worker == "1":
        return True
    if scheduler_worker == "0":
        return False
    # 本地 uvicorn（无 Gunicorn post_fork）不会设置该变量
    return True


def build_service_started_message() -> str:
    """拼装服务启动通知正文（含系统名、环境与监听地址）。"""
    label = get_service_display_name()
    port = get_service_port_hint()
    env_label = "production" if settings.is_production else "development（本机）"
    return (
        f"🚀 【{label}】已启动\n"
        f"系统：{settings.SERVER_NAME}\n"
        f"环境：{env_label}\n"
        f"监听：127.0.0.1:{port}"
    )


def build_service_stopped_message() -> str:
    """拼装服务关闭通知正文。"""
    label = get_service_display_name()
    return f"🧩 【{label}】已关闭\n系统：{settings.SERVER_NAME}"


def notify_service_started() -> bool:
    """
    向管理员 Telegram 发送服务启动通知。

    Returns:
        是否成功发送；TELEGRAM_ENABLE=false 或非负责 worker 时返回 False
    """
    if not getattr(settings, "TELEGRAM_ENABLE", True):
        logger.info("TELEGRAM_ENABLE=false，跳过服务启动通知")
        return False
    if not should_send_service_lifecycle_notify():
        logger.debug("本 worker 不负责发送服务启动通知，已跳过")
        return False
    message = build_service_started_message()
    logger.info("发送服务启动通知：%s", get_service_display_name())
    return send_telegram_message(message)


def notify_service_stopped() -> bool:
    """
    向管理员 Telegram 发送服务关闭通知。

    Returns:
        是否成功发送
    """
    if not getattr(settings, "TELEGRAM_ENABLE", True):
        return False
    if not should_send_service_lifecycle_notify():
        return False
    message = build_service_stopped_message()
    logger.info("发送服务关闭通知：%s", get_service_display_name())
    return send_telegram_message(message)
