"""命令回复失败时的统一日志（识别拉黑等常见 Forbidden）。"""
import logging

logger = logging.getLogger(__name__)


def log_command_reply_failure(command: str, chat_id, exc: BaseException) -> None:
    """按错误类型打清晰日志，避免「命令无反应」时难以排查。"""
    msg = str(exc).lower()
    if "blocked by the user" in msg or "bot was blocked" in msg:
        logger.error(
            "[命令处理器] /%s 已收到，但无法回复 chat_id=%s：用户已拉黑该 Bot。"
            "请在 Telegram 中取消拉黑后对该 Bot 再发 /start。错误：%s",
            command,
            chat_id,
            exc,
        )
        return
    if "chat not found" in msg:
        logger.error(
            "[命令处理器] /%s 已收到，但 chat_id=%s 无效（Chat not found）。错误：%s",
            command,
            chat_id,
            exc,
        )
        return
    if "can't parse entities" in msg or "can't find end of the entity" in msg:
        logger.error(
            "[命令处理器] /%s 回复 chat_id=%s 失败：消息 parse_mode 实体解析错误。错误：%s",
            command,
            chat_id,
            exc,
        )
        return
    logger.error(
        "[命令处理器] /%s 回复 chat_id=%s 失败：%s",
        command,
        chat_id,
        exc,
        exc_info=True,
    )
