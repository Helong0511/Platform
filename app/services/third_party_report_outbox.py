"""
Postback 第三方事件事务性 Outbox。

Outbox 记录与 PostbackConversion 在同一 AsyncSession/事务中提交；
发送 worker 只读取已提交的 Outbox，并在发送时从短链接/斗篷配置引用解析凭据。
Facebook access token 永远不写入此表。
"""
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import func, or_, select

from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.core.third_party_report import (
    REPORT_LOG_LEASE_SECONDS,
    _claim_report_log,
    build_event_idempotency_key,
    send_third_party_report,
    update_report_log,
)
from app.models.models import ShortLink, ThirdPartyReportLog

logger = logging.getLogger(__name__)


async def enqueue_postback_report(
    db,
    *,
    platform: str,
    adsid: str,
    event: str,
    conversion_id: str,
    email: Optional[str],
    ip: Optional[str],
    phone: Optional[str],
    ua: Optional[str],
    currency: Optional[str],
    amount: Optional[float],
    short_link_id: Optional[int],
    cloak_name: Optional[str],
    short_code: Optional[str],
    click_time,
) -> int:
    """只写入当前转化事务，不 commit；返回可恢复的持久化 Outbox 行 ID。"""
    event_key = build_event_idempotency_key(
        "postback", adsid, event, conversion_id, platform=platform
    )
    now = get_app_now_naive()
    existing = await db.scalar(
        select(ThirdPartyReportLog)
        .where(ThirdPartyReportLog.event_key == event_key)
        .with_for_update()
    )
    has_config_reference = bool(short_link_id or (cloak_name and short_code))
    if existing is not None:
        existing.outbox_enqueued = True
        existing.short_link_id = short_link_id
        existing.cloak_name = cloak_name
        existing.short_code = short_code
        existing.click_time = click_time
        existing.max_attempts = max(int(existing.max_attempts or 0), 12)
        if existing.status != "success":
            if has_config_reference:
                existing.status = "pending"
                existing.next_retry_time = now
                existing.error_message = None
            else:
                existing.status = "failed"
                existing.next_retry_time = None
                existing.error_message = "缺少短链接/斗篷配置引用，无法自动解析像素凭据"
        await db.flush()
        return int(existing.id)

    row = ThirdPartyReportLog(
        source="postback",
        adsid=adsid,
        event=event,
        event_key=event_key,
        conversion_id=conversion_id,
        email=email or "",
        ip=ip or "",
        phone=phone or "",
        ua=ua or "",
        currency=currency,
        amount=amount,
        use_hash=True,
        status="pending" if has_config_reference else "failed",
        attempt_count=0,
        max_attempts=12,
        error_message=(
            None if has_config_reference
            else "缺少短链接/斗篷配置引用，无法自动解析像素凭据"
        ),
        outbox_enqueued=True,
        short_link_id=short_link_id,
        cloak_name=cloak_name,
        short_code=short_code,
        click_time=click_time,
        next_retry_time=now if has_config_reference else None,
        created_at=now,
    )
    db.add(row)
    await db.flush()
    return int(row.id)


async def _resolve_pixel_credentials(
    *,
    short_link_id: Optional[int],
    cloak_name: Optional[str],
    short_code: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """只按 Outbox 中的非敏感配置引用解析当前凭据，不读取或持久化旧 token。"""
    pixel_id = None
    access_token = None
    api_version = None
    async with AsyncSessionLocal() as db:
        if short_link_id:
            short_link = await db.scalar(
                select(ShortLink).where(ShortLink.id == short_link_id).limit(1)
            )
            if short_link and short_link.facebook_pixel_id and short_link.facebook_access_token:
                pixel_id = short_link.facebook_pixel_id
                access_token = short_link.facebook_access_token
                api_version = short_link.facebook_api_version

        if not access_token and cloak_name and short_code:
            from app.services.cloak_pixel_mapping import get_cloak_pixel_config

            config = await get_cloak_pixel_config(
                db=db,
                dp=cloak_name,
                short_code=short_code,
                use_cache=False,
            )
            if config:
                pixel_id = config.get("facebook_pixel_id")
                access_token = config.get("facebook_access_token")
                api_version = config.get("facebook_api_version") or api_version

    return pixel_id, access_token, api_version


async def process_postback_report_outbox_item(report_log_id: int) -> dict:
    """处理单条 Outbox；并发由 report_start_time 条件 UPDATE 仲裁。"""
    now = get_app_now_naive()
    async with AsyncSessionLocal() as db:
        row = await db.scalar(
            select(ThirdPartyReportLog)
            .where(
                ThirdPartyReportLog.id == report_log_id,
                ThirdPartyReportLog.outbox_enqueued.is_(True),
            )
            .limit(1)
        )
        if row is None:
            return {"success": False, "reason": "outbox_not_found"}
        if row.status == "success":
            return {"success": True, "deduplicated": True}
        if row.next_retry_time is None or row.next_retry_time > now:
            return {"success": False, "retryable": True, "reason": "not_due"}
        payload = {
            "adsid": row.adsid,
            "event": row.event,
            "conversion_id": row.conversion_id,
            "email": row.email,
            "ip": row.ip,
            "phone": row.phone,
            "ua": row.ua,
            "source": row.source,
            "use_hash": row.use_hash,
            "currency": row.currency,
            "amount": float(row.amount) if row.amount is not None else None,
            "click_time": row.click_time,
            "event_key": row.event_key,
            "short_link_id": row.short_link_id,
            "cloak_name": row.cloak_name,
            "short_code": row.short_code,
        }

    if not (payload["short_link_id"] or (payload["cloak_name"] and payload["short_code"])):
        return {"success": False, "retryable": False, "reason": "missing_config_reference"}

    try:
        pixel_id, access_token, api_version = await _resolve_pixel_credentials(
            short_link_id=payload["short_link_id"],
            cloak_name=payload["cloak_name"],
            short_code=payload["short_code"],
        )
    except Exception as exc:
        logger.warning(
            "Outbox 凭据解析暂时失败，保留待重试：report_log_id=%s error=%s",
            report_log_id,
            exc,
            exc_info=True,
        )
        pixel_id = access_token = api_version = None

    if not pixel_id or not access_token:
        claimed = await _claim_report_log(report_log_id)
        if not claimed:
            return {"success": False, "retryable": True, "reason": "report_in_progress"}
        retry_at = get_app_now_naive() + timedelta(minutes=5)
        await update_report_log(
            report_log_id,
            status="failed",
            error_message="像素凭据暂不可用；Outbox 保留并将在配置恢复后重试",
            report_start_time=get_app_now_naive() - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1),
            completed_at=get_app_now_naive(),
            next_retry_time=retry_at,
        )
        return {"success": False, "retryable": True, "reason": "missing_pixel_credentials"}

    send_result = await send_third_party_report(
        adsid=payload["adsid"],
        event=payload["event"],
        email=payload["email"],
        ip=payload["ip"],
        phone=payload["phone"],
        ua=payload["ua"],
        facebook_pixel_id=pixel_id,
        facebook_access_token=access_token,
        facebook_api_version=api_version,
        source=payload["source"],
        use_hash=payload["use_hash"],
        conversion_id=payload["conversion_id"],
        currency=payload["currency"],
        amount=payload["amount"],
        click_time=payload["click_time"],
        report_log_id=report_log_id,
        event_key=payload["event_key"],
    )
    # 发送函数的成功路径历史上返回 None；读取持久化状态，避免把已成功发送误计为 worker 失败。
    if isinstance(send_result, dict):
        return send_result
    from app.core.third_party_report import _get_report_status

    final_status = await _get_report_status(report_log_id)
    return {
        "success": final_status == "success",
        "retryable": final_status != "success",
        "reason": None if final_status == "success" else "report_status_not_confirmed",
        "report_log_id": report_log_id,
    }


async def process_postback_report_outbox(
    *,
    batch_size: int = 20,
    report_log_id: Optional[int] = None,
) -> dict:
    """扫描已到期的 Outbox；多 worker 可重复扫描，发送租约保证单条互斥。"""
    if batch_size < 1 or batch_size > 100:
        raise ValueError("Outbox batch_size 必须在 1 到 100 之间")
    now = get_app_now_naive()
    stale_before = now - timedelta(seconds=REPORT_LOG_LEASE_SECONDS)
    conditions = [
        ThirdPartyReportLog.outbox_enqueued.is_(True),
        ThirdPartyReportLog.status.in_(("pending", "failed")),
        ThirdPartyReportLog.next_retry_time.is_not(None),
        ThirdPartyReportLog.next_retry_time <= now,
        ThirdPartyReportLog.attempt_count < ThirdPartyReportLog.max_attempts,
        or_(
            ThirdPartyReportLog.report_start_time.is_(None),
            ThirdPartyReportLog.report_start_time < stale_before,
        ),
    ]
    if report_log_id is not None:
        conditions.append(ThirdPartyReportLog.id == report_log_id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ThirdPartyReportLog.id)
            .where(*conditions)
            .order_by(ThirdPartyReportLog.next_retry_time.asc(), ThirdPartyReportLog.id.asc())
            .limit(batch_size)
        )
        report_ids = [int(value) for value in result.scalars().all()]
        # 达到自动重试上限的失败事件不会再进入 due scan，必须单独暴露积压数量。
        exhausted_count = await db.scalar(
            select(func.count(ThirdPartyReportLog.id)).where(
                ThirdPartyReportLog.outbox_enqueued.is_(True),
                ThirdPartyReportLog.status == "failed",
                ThirdPartyReportLog.attempt_count >= ThirdPartyReportLog.max_attempts,
            )
        )

    stats = {
        "selected": len(report_ids),
        "success": 0,
        "retryable": 0,
        "failed": 0,
        "exhausted": int(exhausted_count or 0),
    }
    for report_id in report_ids:
        try:
            result = await process_postback_report_outbox_item(report_id)
            if result.get("success"):
                stats["success"] += 1
            elif result.get("retryable"):
                stats["retryable"] += 1
            else:
                stats["failed"] += 1
        except Exception:
            stats["failed"] += 1
            logger.error("处理 Postback Report Outbox 失败：id=%s", report_id, exc_info=True)
    return stats
