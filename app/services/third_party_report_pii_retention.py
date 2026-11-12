"""第三方上报日志 PII 生命周期清理服务。

只清理已完成或明确耗尽重试的历史事件载荷；保留事件幂等键和审计骨架。
默认关闭，必须在数据保留政策经业务/合规负责人批准后显式配置天数。
"""
import logging
from datetime import timedelta

from sqlalchemy import and_, exists, or_, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.models.third_party import ThirdPartyReportLog
from app.models.postback import PostbackForwardLog, PostbackForwardQueue

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
            "third_party_report_logs_scrubbed": 0,
            "postback_forward_logs_scrubbed": 0,
            "message": "未配置 PII 保留期限，按 fail-safe 策略跳过清理",
        }

    now = get_app_now_naive()
    cutoff = now - timedelta(days=days)
    stale_lease = now - timedelta(seconds=300)
    terminal = and_(
        ThirdPartyReportLog.status.in_(("success", "failed")),
        or_(
            ThirdPartyReportLog.status == "success",
            and_(
                ThirdPartyReportLog.status == "failed",
                or_(
                    ThirdPartyReportLog.outbox_enqueued.is_(False),
                    ThirdPartyReportLog.attempt_count >= ThirdPartyReportLog.max_attempts,
                    ThirdPartyReportLog.error_message == "短链接已删除，无法解析像素配置",
                    # 无配置引用且没有下次重试时间的 Outbox 失败事件不可重排，
                    # 属于终态；否则会永久保留 PII 载荷而永远无法被清理。
                    and_(
                        ThirdPartyReportLog.outbox_enqueued.is_(True),
                        ThirdPartyReportLog.next_retry_time.is_(None),
                        ThirdPartyReportLog.short_link_id.is_(None),
                        or_(
                            ThirdPartyReportLog.cloak_name.is_(None),
                            ThirdPartyReportLog.short_code.is_(None),
                        ),
                    ),
                ),
            ),
        ),
        or_(
            ThirdPartyReportLog.report_start_time.is_(None),
            ThirdPartyReportLog.report_start_time < stale_lease,
        ),
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
            row.adsid = ""
            row.conversion_id = None
            row.short_link_id = None
            row.cloak_name = None
            row.short_code = None
            row.click_time = None
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
        # 下游转发日志也可能包含 URL 参数、请求体、响应正文和失败详情。
        # 仍存在重试队列的目标不能清理，避免影响未完成的投递诊断/重试。
        active_forward_queue = exists(
            select(PostbackForwardQueue.id).where(
                PostbackForwardQueue.conversion_id == PostbackForwardLog.conversion_id,
                # 以完整的目标二元组匹配，避免同一转化的其它目标队列误阻塞；
                # NULL 也必须参与相等判断，兼容产品级/渠道级目标及关联对象删除。
                or_(
                    PostbackForwardQueue.publisher_id == PostbackForwardLog.publisher_id,
                    and_(
                        PostbackForwardQueue.publisher_id.is_(None),
                        PostbackForwardLog.publisher_id.is_(None),
                    ),
                ),
                or_(
                    PostbackForwardQueue.product_id == PostbackForwardLog.product_id,
                    and_(
                        PostbackForwardQueue.product_id.is_(None),
                        PostbackForwardLog.product_id.is_(None),
                    ),
                ),
            )
        )
        forward_result = await db.execute(
            select(PostbackForwardLog)
            .where(
                PostbackForwardLog.created_at < cutoff,
                PostbackForwardLog.completed_at.is_not(None),
                PostbackForwardLog.pii_scrubbed_at.is_(None),
                ~active_forward_queue,
            )
            .order_by(PostbackForwardLog.created_at.asc(), PostbackForwardLog.id.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        forward_rows = list(forward_result.scalars().all())
        for row in forward_rows:
            # downstream_url 非空约束保留，写入固定占位符；原始 URL 不再可恢复。
            row.downstream_url = "[已按保留策略清除]"
            row.request_data = None
            row.request_params = None
            row.response_body = None
            row.error_message = (
                "历史转发载荷已按配置的数据保留策略清除"
                if not row.success
                else None
            )
            row.pii_scrubbed_at = now

        if rows or forward_rows:
            await db.commit()
            logger.info(
                "PII 到期清理完成：third_party=%s postback_forward=%s retention_days=%s",
                len(rows), len(forward_rows), days,
            )
        else:
            await db.rollback()

    total_scrubbed = len(rows) + len(forward_rows)
    return {
        "enabled": True,
        "retention_days": days,
        "selected": total_scrubbed,
        "scrubbed": total_scrubbed,
        "third_party_report_logs_scrubbed": len(rows),
        "postback_forward_logs_scrubbed": len(forward_rows),
        "cutoff": cutoff.isoformat(sep=" "),
        "message": (
            f"已清除 {len(rows)} 条第三方上报日志和 {len(forward_rows)} 条下游转发日志中的个人信息载荷"
        ),
    }


async def scrub_expired_postback_forward_log_pii(
    *,
    retention_days: int | None = None,
    batch_size: int = 200,
) -> dict:
    """清理到期下游转发日志中的请求/响应个人信息，保留最小审计骨架。"""
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

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PostbackForwardLog)
            .where(
                PostbackForwardLog.created_at < cutoff,
                PostbackForwardLog.completed_at.is_not(None),
                PostbackForwardLog.pii_scrubbed_at.is_(None),
                # 有待重试任务时必须保留对应日志，避免破坏自动重试/人工核对链路。
                ~exists(
                    select(PostbackForwardQueue.id).where(
                        PostbackForwardQueue.conversion_id == PostbackForwardLog.conversion_id,
                        or_(
                            PostbackForwardQueue.product_id == PostbackForwardLog.product_id,
                            and_(
                                PostbackForwardQueue.product_id.is_(None),
                                PostbackForwardLog.product_id.is_(None),
                            ),
                        ),
                        or_(
                            PostbackForwardQueue.publisher_id == PostbackForwardLog.publisher_id,
                            and_(
                                PostbackForwardQueue.publisher_id.is_(None),
                                PostbackForwardLog.publisher_id.is_(None),
                            ),
                        ),
                    )
                ),
            )
            .order_by(
                PostbackForwardLog.created_at.asc(),
                PostbackForwardLog.id.asc(),
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars().all())
        for row in rows:
            # 历史 downstream_url 可能已展开 click_id/email 等值，不能保留原 URL。
            row.downstream_url = "已按配置的数据保留策略清除"
            row.request_data = None
            row.request_params = None
            row.response_body = None
            row.error_message = None
            row.pii_scrubbed_at = now
        if rows:
            await db.commit()
            logger.info(
                "Postback 下游转发日志 PII 到期清理完成：scrubbed=%s retention_days=%s",
                len(rows),
                days,
            )
        else:
            await db.rollback()

    return {
        "enabled": True,
        "retention_days": days,
        "selected": len(rows),
        "scrubbed": len(rows),
        "cutoff": cutoff.isoformat(sep=" "),
        "message": f"已清除 {len(rows)} 条下游转发日志中的个人信息载荷",
    }
