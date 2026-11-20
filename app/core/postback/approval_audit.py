"""Postback 审批审计事件写入辅助函数。

成功状态变更必须把审计事件加入同一个 Session/事务后再提交。
拒绝/未授权等没有业务状态变更的尝试，可由调用方使用独立事务持久化。
"""
from typing import Any

from app.models.postback import TelegramPostbackApprovalAudit

_ALLOWED_ACTOR_TYPES = frozenset({"telegram", "system_user", "system"})
_ALLOWED_SOURCES = frozenset({"telegram", "web", "ip_whitelist"})
_ALLOWED_ACTIONS = frozenset({"approve", "reject", "auto_approve"})
_ALLOWED_OUTCOMES = frozenset({
    "approved",
    "rejected",
    "already_exists",
    "denied",
    "not_found",
})


def add_postback_approval_audit(
    db: Any,
    *,
    pending_conversion_id: int | None,
    actor_type: str,
    actor_id: int | str | None,
    source: str,
    action: str,
    outcome: str,
    previous_status: str | None = None,
    new_status: str | None = None,
    conversion_id: int | None = None,
    telegram_callback_query_id: str | None = None,
) -> TelegramPostbackApprovalAudit:
    """将一条最小化审批审计事件加入调用方事务，不在此处 commit。"""
    if actor_type not in _ALLOWED_ACTOR_TYPES:
        raise ValueError("invalid Postback approval audit actor_type")
    if source not in _ALLOWED_SOURCES:
        raise ValueError("invalid Postback approval audit source")
    if action not in _ALLOWED_ACTIONS:
        raise ValueError("invalid Postback approval audit action")
    if outcome not in _ALLOWED_OUTCOMES:
        raise ValueError("invalid Postback approval audit outcome")

    normalized_actor_id = None if actor_id is None else str(actor_id).strip()
    if normalized_actor_id == "":
        normalized_actor_id = None
    if normalized_actor_id is not None and len(normalized_actor_id) > 64:
        raise ValueError("Postback approval audit actor_id is too long")

    normalized_callback_id = (
        None
        if telegram_callback_query_id is None
        else str(telegram_callback_query_id).strip()
    )
    if normalized_callback_id == "":
        normalized_callback_id = None
    if normalized_callback_id is not None and len(normalized_callback_id) > 128:
        raise ValueError("Postback approval audit callback id is too long")

    event = TelegramPostbackApprovalAudit(
        pending_conversion_id=pending_conversion_id,
        conversion_id=conversion_id,
        actor_type=actor_type,
        actor_id=normalized_actor_id,
        source=source,
        action=action,
        outcome=outcome,
        previous_status=previous_status,
        new_status=new_status,
        telegram_callback_query_id=normalized_callback_id,
    )
    db.add(event)
    return event
