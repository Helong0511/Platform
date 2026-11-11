"""第三方上报日志 PII 生命周期清理服务。

只清理已完成或明确耗尽重试的历史事件载荷；保留事件幂等键和审计骨架。
默认关闭，必须在数据保留政策经业务/合规负责人批准后显式配置天数。
"""
import logging
from datetime import timedelta

from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.models.third_party import ThirdPartyReportLog

logger = logging.getLogger(__name__)


async def scrub_expired_third_party_report_pii(
    *,
    retention_days: int | None = None,
    batch_size: int = 200,
) -> dict:
    """分批清除到期终态日志中的 PII，不删除事件记录或 event_key。"""
    days = (
        int(settings.THIRD_PARTY_REPORT_PII_RETENTION_DAYS)
        if retention_days is None
        else int(retention_days)
    )
    if days < 0:
        raise ValueError("第三方上报 PII 保留天数不能小于 0")
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("PII 清理 batch_size 必须在 1 到 1000 之间")
    if days == 0:
        return {
            "enabled": False,
            "retention_days": 0,
            "selected": 0,
            "scrubbed": 0,
            "message": "未配置 PII 保留期限，按 fail-safe 策略跳过清理",
        }

    now = get_app_now_naive()
    cutoff = now - timedelta(days=days)
    stale_lease = now - timedelta(seconds=300)
    terminal = or_(
        ThirdPartyReportLog.status == "success",
        and_(
            ThirdPartyReportLog.status == "failed",
            ThirdPartyReportLog.next_retry_time.is_(None),
            ThirdPartyReportLog.attempt_count >= ThirdPartyReportLog.max_attempts,
            or_(
                ThirdPartyReportLog.report_start_time.is_(None),
                ThirdPartyReportLog.report_start_time < stale_lease,
            ),
        ),
        # 旧的非 Outbox 日志没有后台重试能力，可按相同保留策略清理。
        ThirdPartyReportLog.outbox_enqueued.is_(False),
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ThirdPartyReportLog)
            .where(
                ThirdPartyReportLog.created_at < cutoff,
                ThirdPartyReportLog.pii_scrubbed_at.is_(None),
                terminal,
            )
            .order_by(ThirdPartyReportLog.created_at.asc(), ThirdPartyReportLog.id.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars().all())
        for row in rows:
            # 保留 event_key/source/event/status/金额和时间，防止幂等去重及审计断链。
            row.email = None
            row.ip = None
            row.phone = None
            row.ua = None
            row.report_params = None
            row.response_body = None
            row.log_id = None
            row.error_message = (
                "历史上报载荷已按配置的数据保留策略清除"
                if row.status == "failed"
                else None
            )
            row.pii_scrubbed_at = now
        if rows:
            await db.commit()
        else:
            await db.rollback()

    return {
        "enabled": True,
        "retention_days": days,
        "selected": len(rows),
        "scrubbed": len(rows),
        "cutoff": cutoff.isoformat(sep=" "),
        "message": f"已清除 {len(rows)} 条终态上报记录中的个人信息载荷",
    }
