"""
第三方广告上报模块
独立于其他模块，避免循环导入问题
"""
import asyncio
import logging
import time
import httpx
import hashlib
import json
from typing import Optional
from datetime import datetime, timedelta

from sqlalchemy import select, update, or_
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telegram.message_sender import send_telegram_message_async as send_telegram_message
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.models.models import ThirdPartyReportLog, ThirdPartyReportIdentityLock
from app.core.log_utils import mask_email, mask_hash_prefix, mask_phone

logger = logging.getLogger(__name__)


REPORT_LOG_LEASE_SECONDS = 300
# HTTPX 的 read timeout 限制相邻数据块之间的等待时间，不限制整个响应的墙钟时长。
# 单次请求总时限必须明显短于租约，避免慢速持续回包让旧 Worker 长期占有请求。
REPORT_HTTP_REQUEST_DEADLINE_SECONDS = 60


def _report_http_request_deadline_seconds() -> float:
    """单次 HTTP 总时限最多占租约的一半，为结果落库和调度留出安全余量。"""
    if REPORT_LOG_LEASE_SECONDS <= 0 or REPORT_HTTP_REQUEST_DEADLINE_SECONDS <= 0:
        raise ValueError("第三方上报租约和 HTTP 总时限必须为正数")
    return min(
        float(REPORT_HTTP_REQUEST_DEADLINE_SECONDS),
        REPORT_LOG_LEASE_SECONDS / 2,
    )


async def _post_with_total_deadline(client, url, *, json, params):
    """在 HTTPX 网络阶段超时之外，再限制整个请求的总墙钟时长。"""
    return await asyncio.wait_for(
        client.post(url, json=json, params=params),
        timeout=_report_http_request_deadline_seconds(),
    )


def sha256_hash(value: Optional[str]) -> str:
    """
    对字符串进行 SHA256 哈希处理
    Facebook 要求：先规范化（去除前后空格，转小写），然后 SHA256 哈希
    """
    if not value:
        return ""
    normalized_value = value.strip().lower()
    return hashlib.sha256(normalized_value.encode('utf-8')).hexdigest()


def _report_base_identity_value(
    source: str,
    adsid: str,
    event: str,
    conversion_id: Optional[str] = None,
) -> str:
    """构建四字段基础身份的无歧义编码，供事件键与跨入口锁共同使用。"""
    # ViewContent 的 conversion_id 只是后补关联元数据，不属于基础身份。
    identity_conversion_id = "" if event == "ViewContent" else (conversion_id or "")
    parts = (source or "", adsid or "", event or "", identity_conversion_id)
    return "".join(f"{len(part)}:{part}" for part in parts)


def build_event_idempotency_key(
    source: str,
    adsid: str,
    event: str,
    conversion_id: Optional[str] = None,
    platform: Optional[str] = None,
) -> str:
    """构建稳定的事件身份键；同一事件的重试保持不变，不同事件互不覆盖。"""
    identity = _report_base_identity_value(source, adsid, event, conversion_id)
    normalized_platform = (platform or "").strip()
    if normalized_platform:
        identity += f"{len(normalized_platform)}:{normalized_platform}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


async def _lock_report_base_identity(
    db,
    *,
    source: str,
    adsid: str,
    event: str,
    conversion_id: Optional[str],
) -> str:
    """在当前业务事务内取得跨直接发送/Outbox 共用的基础身份行锁。

    锁行永久保留；INSERT ... ON DUPLICATE KEY UPDATE 与 SELECT FOR UPDATE
    在同一事务/连接上执行，确保首次建锁行和后续锁定都可被并发事务串行化。
    """
    # 原始 adsid 等身份字段只在内存中参与编码；锁表仅保留独立 SHA-512 指纹。
    identity_value = _report_base_identity_value(source, adsid, event, conversion_id).encode("utf-8")
    identity_key = hashlib.sha256(identity_value).hexdigest()
    identity_fingerprint = hashlib.sha512(identity_value).digest()
    statement = mysql_insert(ThirdPartyReportIdentityLock).values(
        identity_key=identity_key,
        identity_fingerprint=identity_fingerprint,
    )
    statement = statement.on_duplicate_key_update(
        identity_key=statement.inserted.identity_key
    )
    await db.execute(statement)
    result = await db.execute(
        select(ThirdPartyReportIdentityLock)
        .where(ThirdPartyReportIdentityLock.identity_key == identity_key)
        .with_for_update()
    )
    lock_row = result.scalars().first()
    if lock_row is None or bytes(lock_row.identity_fingerprint) != identity_fingerprint:
        raise RuntimeError("第三方事件身份锁缺失或检测到 SHA-256 碰撞")
    return identity_key


async def _has_legacy_unresolved_base_identity(
    db,
    *,
    source: str,
    adsid: str,
    event: str,
    conversion_id: Optional[str],
) -> bool:
    """在基础身份锁内查找所有无法证明平台归属的历史事件。

    旧版平台 Outbox 的 event_key 可能包含 platform，但旧模型没有持久化
    platform。不能只查四字段/当前五字段 event_key，否则会漏掉其它平台
    的 legacy_unresolved 行并允许重复创建。
    """
    query = select(ThirdPartyReportLog.id).where(
        ThirdPartyReportLog.source == source,
        ThirdPartyReportLog.adsid == adsid,
        ThirdPartyReportLog.event == event,
        ThirdPartyReportLog.identity_scope == "legacy_unresolved",
    )
    # ViewContent 的 conversion_id 是后补元数据，不属于基础身份。
    if event != "ViewContent":
        if conversion_id:
            query = query.where(ThirdPartyReportLog.conversion_id == conversion_id)
        else:
            # 历史数据可能分别以 NULL 或空字符串表示“没有 conversion_id”；
            # 幂等键算法将两者规范为同一个空值，冲突查询也必须一致。
            query = query.where(
                or_(
                    ThirdPartyReportLog.conversion_id.is_(None),
                    ThirdPartyReportLog.conversion_id == "",
                )
            )
    result = await db.execute(query.limit(1).with_for_update())
    return result.scalars().first() is not None


async def create_report_log(
        source: str,
        adsid: str,
        event: str,
        email: str,
        ip: str,
        phone: str,
        ua: str,
        max_attempts: int = 3,
        use_hash: bool = True,
        report_params: Optional[str] = None,
        conversion_id: Optional[str] = None,
        currency: Optional[str] = None,
        amount: Optional[float] = None,
        destination_pixel_id: Optional[str] = None,
) -> int:
    """创建明确标记为 unscoped 的直接发送日志；历史/平台作用域记录不得被误复用。"""
    event_key = build_event_idempotency_key(source, adsid, event, conversion_id)

    def reusable_unscoped_row(row) -> bool:
        return bool(
            row
            and getattr(row, "identity_scope", None) == "unscoped"
            and getattr(row, "platform", None) is None
            and (getattr(row, "destination_pixel_id", None) or None)
            == (destination_pixel_id or None)
        )

    try:
        async with AsyncSessionLocal() as db:
            await _lock_report_base_identity(
                db,
                source=source,
                adsid=adsid,
                event=event,
                conversion_id=conversion_id,
            )
            if await _has_legacy_unresolved_base_identity(
                db,
                source=source,
                adsid=adsid,
                event=event,
                conversion_id=conversion_id,
            ):
                logger.warning(
                    "[第三方上报] 基础身份存在平台归属未确认的历史事件，拒绝创建直接发送事件"
                )
                return 0
            # 同一基础身份下，平台作用域事件与无平台直接发送事件不可并存。
            scoped_query = select(ThirdPartyReportLog.id).where(
                ThirdPartyReportLog.source == source,
                ThirdPartyReportLog.adsid == adsid,
                ThirdPartyReportLog.event == event,
                ThirdPartyReportLog.identity_scope == "platform_scoped",
            )
            if event != "ViewContent":
                scoped_query = scoped_query.where(
                    ThirdPartyReportLog.conversion_id == conversion_id
                )
            scoped_result = await db.execute(scoped_query.limit(1))
            scoped_conflict = scoped_result.scalars().first()
            if scoped_conflict is not None:
                logger.warning(
                    "[第三方上报] 相同基础身份已存在平台作用域事件，拒绝创建无平台事件"
                )
                return 0
            result = await db.execute(
                select(ThirdPartyReportLog)
                .where(ThirdPartyReportLog.event_key == event_key)
                .limit(1)
            )
            existing = result.scalars().first()
            if existing is not None:
                if not reusable_unscoped_row(existing):
                    logger.warning(
                        "[第三方上报] 事件身份已存在但作用域/Pixel 目的地不匹配，拒绝复用：source=%s event=%s",
                        source,
                        event,
                    )
                    return 0
                return int(existing.id)

            log_entry = ThirdPartyReportLog(
                source=source,
                adsid=adsid,
                event=event,
                event_key=event_key,
                conversion_id=conversion_id,
                platform=None,
                identity_scope="unscoped",
                destination_pixel_id=destination_pixel_id or None,
                email=email,
                ip=ip,
                phone=phone,
                ua=ua,
                currency=currency,
                amount=amount,
                use_hash=use_hash,
                report_params=report_params,
                status="pending",
                attempt_count=0,
                max_attempts=max_attempts,
                created_at=get_app_now_naive(),
                next_retry_time=get_app_now_naive(),
            )
            db.add(log_entry)
            await db.commit()
            await db.refresh(log_entry)
            return log_entry.id
    except IntegrityError:
        # 唯一键竞争后必须重新验证 scope 和 Pixel 目的地，不能仅按 event_key 复用。
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(ThirdPartyReportLog)
                    .where(ThirdPartyReportLog.event_key == event_key)
                    .limit(1)
                )
                existing = result.scalars().first()
                if reusable_unscoped_row(existing):
                    return int(existing.id)
                logger.warning(
                    "[第三方上报] 并发创建冲突后身份归属/目的地不匹配，拒绝复用"
                )
        except Exception as lookup_exc:
            logger.warning(
                "[第三方上报] 并发创建冲突后读取事件日志失败：%s",
                type(lookup_exc).__name__,
            )
    except Exception as exc:
        logger.warning("[第三方上报] 创建日志记录失败：%s", type(exc).__name__)
    return 0

async def update_report_log(
        log_id: int,
        status: Optional[str] = None,
        attempt_count: Optional[int] = None,
        response_status: Optional[int] = None,
        response_body: Optional[str] = None,
        log_id_from_response: Optional[str] = None,
        error_message: Optional[str] = None,
        report_start_time: Optional[datetime] = None,
        report_success_time: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        report_params: Optional[str] = None,
        next_retry_time: Optional[datetime] = None,
        clear_next_retry_time: bool = False,
        expected_report_start_time: Optional[datetime] = None,
        expected_identity_scope: Optional[str] = "unscoped",
        expected_platform: Optional[str] = None,
):
    """
    更新第三方上报日志记录
    """
    if not log_id:
        return False
    try:
        async with AsyncSessionLocal() as db:
            query = select(ThirdPartyReportLog).where(ThirdPartyReportLog.id == log_id)
            if expected_report_start_time is not None:
                # 租约令牌与身份作用域必须同时匹配；过期/错平台 Worker 不得覆盖其它事件。
                if expected_identity_scope not in {"unscoped", "platform_scoped"}:
                    return False
                if expected_identity_scope == "platform_scoped" and not (expected_platform or "").strip():
                    return False
                if expected_identity_scope == "unscoped" and expected_platform:
                    return False
                query = query.where(
                    ThirdPartyReportLog.report_start_time == expected_report_start_time,
                    ThirdPartyReportLog.identity_scope == expected_identity_scope,
                    (
                        ThirdPartyReportLog.platform == expected_platform
                        if expected_identity_scope == "platform_scoped"
                        else ThirdPartyReportLog.platform.is_(None)
                    ),
                    ThirdPartyReportLog.pii_scrubbed_at.is_(None),
                )
            result = await db.execute(query.with_for_update())
            log_entry = result.scalars().first()
            if log_entry:
                if status is not None:
                    log_entry.status = status
                if attempt_count is not None:
                    log_entry.attempt_count = attempt_count
                if response_status is not None:
                    log_entry.response_status = response_status
                if response_body is not None:
                    log_entry.response_body = response_body
                if log_id_from_response is not None:
                    log_entry.log_id = log_id_from_response
                if error_message is not None:
                    log_entry.error_message = error_message
                if report_start_time is not None:
                    log_entry.report_start_time = report_start_time
                if report_success_time is not None:
                    log_entry.report_success_time = report_success_time
                if completed_at is not None:
                    log_entry.completed_at = completed_at
                if report_params is not None:
                    log_entry.report_params = report_params
                if next_retry_time is not None:
                    log_entry.next_retry_time = next_retry_time
                if clear_next_retry_time:
                    log_entry.next_retry_time = None
                await db.commit()
                return True
            return False
    except Exception as e:
        logger.warning("[第三方上报] 更新日志记录失败：%s", type(e).__name__)
        return False


async def _get_report_status(report_log_id: int) -> Optional[str]:
    """读取事件上报状态；读取失败由调用方按不可安全发送处理。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ThirdPartyReportLog.status)
            .where(ThirdPartyReportLog.id == report_log_id)
            .limit(1)
        )
        return result.scalar_one_or_none()


async def _validate_existing_report_log_binding(
    report_log_id: int,
    *,
    source: str,
    adsid: str,
    event: str,
    conversion_id: Optional[str],
    event_key: Optional[str],
    platform: Optional[str],
    destination_pixel_id: Optional[str],
    lease_token: Optional[datetime] = None,
) -> bool:
    """发送前验证 Outbox 日志、平台作用域、目的地与载荷身份一致。"""
    if not report_log_id or not event_key or not platform or not destination_pixel_id:
        return False

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ThirdPartyReportLog)
            .where(ThirdPartyReportLog.id == report_log_id)
            .limit(1)
        )
        row = result.scalars().first()

    if row is None:
        return False
    if not bool(getattr(row, "outbox_enqueued", False)):
        return False
    if getattr(row, "identity_scope", None) != "platform_scoped":
        return False
    if getattr(row, "platform", None) != platform:
        return False
    if getattr(row, "destination_pixel_id", None) != destination_pixel_id:
        return False
    if getattr(row, "pii_scrubbed_at", None) is not None:
        return False

    # 严格比较持久化身份字段，不能让调用方把任意 payload 绑定到另一个日志 ID。
    if (
        row.source != source
        or row.adsid != adsid
        or row.event != event
        or row.conversion_id != conversion_id
        or row.event_key != event_key
    ):
        return False

    # Outbox Worker 已认领时，必须仍持有同一个秒级租约；防止旧快照跨租约接管发送。
    if lease_token is not None and row.report_start_time != lease_token:
        return False
    return True


async def _get_report_attempt_state(
    report_log_id: int,
    *,
    expected_scope: str,
    platform: Optional[str] = None,
) -> tuple[int, int]:
    """按预期身份作用域读取累计尝试次数，避免仅凭 ID 读取其它作用域事件。"""
    if expected_scope not in {"unscoped", "platform_scoped"}:
        raise RuntimeError("第三方上报身份作用域无效")
    if expected_scope == "platform_scoped" and not (platform or "").strip():
        raise RuntimeError("第三方上报平台作用域缺少平台标识")
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ThirdPartyReportLog.attempt_count, ThirdPartyReportLog.max_attempts)
            .where(
                ThirdPartyReportLog.id == report_log_id,
                ThirdPartyReportLog.identity_scope == expected_scope,
                (
                    ThirdPartyReportLog.platform == platform
                    if expected_scope == "platform_scoped"
                    else ThirdPartyReportLog.platform.is_(None)
                ),
            )
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            raise RuntimeError("第三方上报日志不存在或身份作用域不匹配")
        return max(0, int(row[0] or 0)), max(1, int(row[1] or 1))


def _calculate_report_attempt_budget(
    base_attempt_count: int,
    max_attempts_total: int,
    *,
    use_hash: bool,
    max_retries: int,
) -> tuple[int, bool]:
    """计算本轮哈希请求数与非哈希兜底，严格不超过累计尝试预算。"""
    remaining = max(0, int(max_attempts_total) - max(0, int(base_attempt_count)))
    if remaining == 0:
        return 0, False
    hash_attempts = min(
        max(0, int(max_retries)),
        max(0, remaining - (1 if use_hash else 0)),
    )
    fallback_allowed = bool(use_hash and remaining > hash_attempts)
    return hash_attempts, fallback_allowed


async def _claim_report_log(
    report_log_id: int,
    lease_seconds: int = REPORT_LOG_LEASE_SECONDS,
    *,
    expected_scope: Optional[str] = "unscoped",
    platform: Optional[str] = None,
) -> Optional[datetime]:
    """原子认领事件并返回秒级租约令牌；失败返回 None。

    失败状态允许立即重试；pending 状态仅允许首次认领或租约过期后恢复。
    发送进程异常退出时，租约到期后可由后续请求接管；旧 Worker 的令牌随即失效。
    """
    if expected_scope not in {"unscoped", "platform_scoped"}:
        return None
    if expected_scope == "platform_scoped" and not (platform or "").strip():
        return None
    if expected_scope == "unscoped" and platform:
        return None

    # MySQL DATETIME 默认精度为秒，令牌必须先截断微秒，保证回读/比较一致。
    now = get_app_now_naive().replace(microsecond=0)
    stale_before = now - timedelta(seconds=max(30, lease_seconds))
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(ThirdPartyReportLog)
            .where(
                ThirdPartyReportLog.id == report_log_id,
                ThirdPartyReportLog.identity_scope == expected_scope,
                (
                    ThirdPartyReportLog.platform == platform
                    if expected_scope == "platform_scoped"
                    else ThirdPartyReportLog.platform.is_(None)
                ),
                ThirdPartyReportLog.status.in_(("pending", "failed")),
                # PII 清理与发送认领必须在同一行锁/条件 UPDATE 上仲裁：
                # 若清理先提交，已复制到 Worker 内存的旧载荷也不得再发送。
                ThirdPartyReportLog.pii_scrubbed_at.is_(None),
                # 认领阶段即阻止耗尽预算的事件，避免空转占用 5 分钟租约。
                ThirdPartyReportLog.attempt_count < ThirdPartyReportLog.max_attempts,
                or_(
                    ThirdPartyReportLog.report_start_time.is_(None),
                    ThirdPartyReportLog.report_start_time < stale_before,
                ),
                or_(
                    ThirdPartyReportLog.next_retry_time.is_(None),
                    ThirdPartyReportLog.next_retry_time <= now,
                ),
            )
            .values(report_start_time=now)
        )
        await db.commit()
        return now if (result.rowcount or 0) == 1 else None


async def _renew_report_log_lease(
    report_log_id: int,
    lease_token: datetime,
    lease_seconds: int = REPORT_LOG_LEASE_SECONDS,
    *,
    expected_scope: Optional[str] = "unscoped",
    platform: Optional[str] = None,
) -> Optional[datetime]:
    """仅允许尚未过期的当前持有者续租；过期令牌不可复活。"""
    if expected_scope not in {"unscoped", "platform_scoped"}:
        return None
    if expected_scope == "platform_scoped" and not (platform or "").strip():
        return None
    if expected_scope == "unscoped" and platform:
        return None
    now = get_app_now_naive().replace(microsecond=0)
    valid_after = now - timedelta(seconds=max(30, lease_seconds))
    async with AsyncSessionLocal() as db:
        # MySQL DATETIME 默认秒级精度：认领后同一秒内续租会写入相同值，
        # 某些驱动按 changed rows 返回 rowcount=0。此时只做所有权/有效期确认，
        # 不把仍然有效的当前租约误判为丢失，也不伪造一次续租。
        if now <= lease_token:
            result = await db.execute(
                select(ThirdPartyReportLog.report_start_time).where(
                    ThirdPartyReportLog.id == report_log_id,
                    ThirdPartyReportLog.identity_scope == expected_scope,
                    (
                        ThirdPartyReportLog.platform == platform
                        if expected_scope == "platform_scoped"
                        else ThirdPartyReportLog.platform.is_(None)
                    ),
                    ThirdPartyReportLog.report_start_time == lease_token,
                    ThirdPartyReportLog.report_start_time >= valid_after,
                    ThirdPartyReportLog.pii_scrubbed_at.is_(None),
                    ThirdPartyReportLog.status.in_(("pending", "failed")),
                )
            )
            current_token = result.scalar_one_or_none()
            return lease_token if current_token == lease_token else None

        result = await db.execute(
            update(ThirdPartyReportLog)
            .where(
                ThirdPartyReportLog.id == report_log_id,
                ThirdPartyReportLog.identity_scope == expected_scope,
                (
                    ThirdPartyReportLog.platform == platform
                    if expected_scope == "platform_scoped"
                    else ThirdPartyReportLog.platform.is_(None)
                ),
                ThirdPartyReportLog.report_start_time == lease_token,
                ThirdPartyReportLog.report_start_time >= valid_after,
                ThirdPartyReportLog.pii_scrubbed_at.is_(None),
                ThirdPartyReportLog.status.in_(("pending", "failed")),
            )
            .values(report_start_time=now)
        )
        await db.commit()
        return now if (result.rowcount or 0) == 1 else None


async def _link_purchase_to_view_content(
    *,
    source: str,
    adsid: str,
    conversion_id: str,
    report_log_id: int,
    destination_pixel_id: Optional[str],
    identity_scope: str,
    platform: Optional[str],
) -> bool:
    """只关联同一身份作用域、同一 Pixel 目的地的 ViewContent。"""
    if not destination_pixel_id:
        logger.info(
            "[第三方上报] 跳过 ViewContent 关联：缺少可验证的 Pixel 目的地：report_log_id=%s",
            report_log_id,
        )
        return False
    if identity_scope not in {"unscoped", "platform_scoped"}:
        return False
    if identity_scope == "platform_scoped" and not (platform or "").strip():
        return False
    if identity_scope == "unscoped" and platform:
        return False

    try:
        async with AsyncSessionLocal() as db:
            query = (
                select(ThirdPartyReportLog)
                .where(ThirdPartyReportLog.source == source)
                .where(ThirdPartyReportLog.adsid == adsid)
                .where(ThirdPartyReportLog.event == "ViewContent")
                .where(ThirdPartyReportLog.conversion_id.is_(None))
                .where(ThirdPartyReportLog.identity_scope == identity_scope)
                .where(ThirdPartyReportLog.destination_pixel_id == destination_pixel_id)
            )
            if identity_scope == "platform_scoped":
                query = query.where(ThirdPartyReportLog.platform == platform)
            else:
                query = query.where(ThirdPartyReportLog.platform.is_(None))
            # 同一个 ViewContent 只能被一个 Purchase 认领；锁定候选行并稳定排序，
            # 避免两个不同 conversion_id 并发读取同一条 NULL 记录后互相覆盖。
            result = await db.execute(
                query.order_by(ThirdPartyReportLog.id.asc()).limit(1).with_for_update()
            )
            view_content_log = result.scalars().first()
            if view_content_log:
                view_content_log.conversion_id = conversion_id
                await db.commit()
                logger.info(
                    "[第三方上报] 已关联同作用域/同 Pixel 的 ViewContent：report_log_id=%s",
                    report_log_id,
                )
                return True
            logger.info(
                "[第三方上报] 未找到同作用域/同 Pixel 的 ViewContent：report_log_id=%s",
                report_log_id,
            )
    except Exception as exc:
        logger.warning(
            "[第三方上报] 关联 ViewContent 事件失败：%s",
            type(exc).__name__,
        )
    return False


async def send_third_party_report(
        adsid: str,
        event: str,
        email: Optional[str],
        ip: Optional[str],
        phone: Optional[str],
        ua: Optional[str],
        facebook_pixel_id: str,  # 必须参数
        facebook_access_token: str,  # 必须参数
        source: str = "unknown",
        use_hash: bool = True,
        conversion_id: Optional[str] = None,
        currency: Optional[str] = None,
        amount: Optional[float] = None,
        click_time: Optional[datetime] = None,
        facebook_api_version: Optional[str] = "v23.0",  # 可选参数，默认与全局 FACEBOOK_API_VERSION 对齐
        platform: Optional[str] = None,
        report_log_id: Optional[int] = None,
        event_key: Optional[str] = None,
        report_lease_token: Optional[datetime] = None,
):
    """
    后台任务：发送第三方广告上报
    从服务器端发送，避免浏览器 CORS 和广告拦截器问题
    包含智能重试机制，确保网络问题时仍能成功上报

    参数要求：
    - ViewContent 事件：email, ip, phone, ua 必须提供
    - Purchase 事件：email, ip, phone, ua 必须提供
    
    必须参数：
    - facebook_pixel_id: Facebook Pixel ID（必须）
    - facebook_access_token: Facebook Access Token（必须）
    
    可选参数：
    - click_time: 点击时间（datetime 对象），如果提供，将使用该时间作为 event_time
    - conversion_id: 转化 ID（Purchase 事件必需）
    - currency: 货币类型（默认为 USD）
    - amount: 金额（Purchase 事件必需）
    - facebook_api_version: Facebook API 版本（可选，默认 v21.0）
    """
    max_retries = 3
    base_delay = 1  # 基础延迟时间（秒）
    timeout = 5  # 超时时间（秒）
    failure_reasons = []  # 收集失败原因

    # 统一清理字段，避免 None 影响日志入库与参数构造
    email = (email or "").strip()
    phone = (phone or "").strip()
    ip = (ip or "").strip()
    ua = (ua or "").strip()
    adsid = (adsid or "").strip()

    # platform 只允许由持久化 Outbox 入口提供；直接发送必须明确保持 unscoped。
    if report_log_id is None and platform:
        return {"success": False, "retryable": False, "reason": "invalid_report_identity_scope"}

    # 既有日志 ID 只能发送其持久化 Outbox 载荷；校验必须先于凭证分支、租约认领和 HTTP。
    if report_log_id is not None:
        try:
            binding_valid = await _validate_existing_report_log_binding(
                report_log_id,
                source=source,
                adsid=adsid,
                event=event,
                conversion_id=conversion_id,
                event_key=event_key,
                platform=platform,
                destination_pixel_id=(facebook_pixel_id or "").strip(),
                lease_token=report_lease_token,
            )
        except Exception as binding_exc:
            logger.warning(
                "[第三方上报] 既有日志身份核验不可用，拒绝发送：id=%s error_type=%s",
                report_log_id,
                type(binding_exc).__name__,
            )
            return {"success": False, "retryable": True, "reason": "report_identity_check_unavailable"}
        if not binding_valid:
            logger.warning(
                "[第三方上报] 既有日志与发送载荷不匹配，拒绝发送：id=%s",
                report_log_id,
            )
            return {"success": False, "retryable": False, "reason": "report_identity_mismatch"}

    # 像素凭证须由调用方显式传入（短链 / 斗篷）；不再回退全局 FACEBOOK_*
    pixel_id = (facebook_pixel_id or "").strip()
    access_token = (facebook_access_token or "").strip()
    api_version = (facebook_api_version or settings.FACEBOOK_API_VERSION or "v23.0").strip()
    if not pixel_id or not access_token:
        logger.warning(
            "[第三方上报] 缺少像素凭证，暂缓 Facebook CAPI：event=%s pixel_id=%s",
            event,
            "empty" if not pixel_id else pixel_id[:10],
        )
        if report_log_id:
            lease_token = report_lease_token or await _claim_report_log(
                report_log_id,
                expected_scope="platform_scoped",
                platform=platform,
            )
            if lease_token is None:
                existing_status = await _get_report_status(report_log_id)
                if existing_status == "success":
                    return {"success": True, "deduplicated": True, "report_log_id": report_log_id}
                return {"success": False, "retryable": True, "reason": "report_in_progress"}
            now = get_app_now_naive()
            updated = await update_report_log(
                report_log_id,
                status="failed",
                error_message="像素凭证暂不可用，Outbox 将自动重试",
                report_start_time=now - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1),
                completed_at=now,
                next_retry_time=now + timedelta(minutes=5),
                expected_report_start_time=lease_token,
                expected_identity_scope="platform_scoped",
                expected_platform=platform,
            )
            if not updated:
                return {"success": False, "retryable": True, "reason": "report_lease_lost"}
            return {"success": False, "retryable": True, "reason": "missing_facebook_credentials"}
        return {
            "success": False,
            "skipped": True,
            "reason": "missing_facebook_credentials",
        }

    # 直接发送路径创建日志；事务性 Outbox 路径复用转化事务中已提交的日志行。
    using_existing_report_log = bool(report_log_id)
    if not report_log_id:
        report_log_id = await create_report_log(
            source=source,
            adsid=adsid,
            event=event,
            email=email,
            ip=ip,
            phone=phone,
            ua=ua,
            max_attempts=max_retries,
            use_hash=use_hash,
            conversion_id=conversion_id,
            destination_pixel_id=pixel_id,
            currency=currency,
            amount=amount,
        )

    if not report_log_id:
        error_msg = "创建上报日志记录失败"
        logger.error(f"[第三方上报] {error_msg}")
        raise ValueError(error_msg)

    event_key = event_key or build_event_idempotency_key(
        source, adsid, event, conversion_id, platform=platform
    )
    try:
        lease_token = report_lease_token or await _claim_report_log(
            report_log_id,
            expected_scope="platform_scoped" if using_existing_report_log else "unscoped",
            platform=platform,
        )
        if lease_token is None:
            existing_status = await _get_report_status(report_log_id)
            if existing_status == "success":
                logger.info(
                    "[第三方上报] 相同事件已成功上报，跳过重复发送: report_log_id=%s event=%s",
                    report_log_id,
                    event,
                )
                return {"success": True, "deduplicated": True, "report_log_id": report_log_id}
            return {
                "success": False,
                "retryable": True,
                "reason": "report_in_progress",
                "report_log_id": report_log_id,
            }
    except Exception as claim_exc:
        # 无法确认是否成功认领时禁止发送，避免并发重复上报。
        logger.error(
            "[第三方上报] 事件认领失败，跳过发送：id=%s error_type=%s",
            report_log_id,
            type(claim_exc).__name__,
        )
        return {"success": False, "retryable": True, "reason": "report_claim_unavailable"}

    async def update_owned_report_log(*args, **kwargs):
        """只允许当前租约持有者更新状态，阻止过期 Worker 覆盖新 Worker。"""
        return await update_report_log(
            *args,
            expected_report_start_time=lease_token,
            expected_identity_scope="platform_scoped" if using_existing_report_log else "unscoped",
            expected_platform=platform,
            **kwargs,
        )

    async def renew_owned_report_lease() -> bool:
        """发送前续租并验证令牌；过期 Worker 必须 fail closed。"""
        nonlocal lease_token
        renewed_token = await _renew_report_log_lease(
            report_log_id,
            lease_token,
            expected_scope="platform_scoped" if using_existing_report_log else "unscoped",
            platform=platform,
        )
        if renewed_token is None:
            return False
        lease_token = renewed_token
        return True

    if using_existing_report_log:
        base_attempt_count, max_attempts_total = await _get_report_attempt_state(
            report_log_id,
            expected_scope="platform_scoped",
            platform=platform,
        )
    else:
        base_attempt_count = 0
        max_attempts_total = max_retries + (1 if use_hash else 0)
    if base_attempt_count >= max_attempts_total:
        # 不留住刚取得的租约；该事件已耗尽预算，不得继续发起外部请求。
        await update_owned_report_log(
            report_log_id,
            status="failed",
            report_start_time=get_app_now_naive() - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1),
            completed_at=get_app_now_naive(),
            clear_next_retry_time=True,
        )
        return {"success": False, "retryable": False, "reason": "max_attempts_exhausted"}

    # 每次 Worker 执行的总请求数（哈希请求 + 可选非哈希兜底）不得超过
    # 数据库中剩余的累计预算，防止接近上限时仍固定发送 4 次而超额。
    hash_attempts, fallback_allowed = _calculate_report_attempt_budget(
        base_attempt_count,
        max_attempts_total,
        use_hash=use_hash,
        max_retries=max_retries,
    )

    async def _mark_failed_and_raise(error_msg: str):
        """将上报日志标为 failed 后抛出 ValueError，供上层中断流程。"""
        logger.error(f"[第三方上报] {error_msg}")
        await update_owned_report_log(
            report_log_id,
            status="failed",
            error_message=error_msg,
            # 将租约标记为已释放，允许失败事件立即被后续重试认领。
            report_start_time=get_app_now_naive() - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1),
            completed_at=get_app_now_naive(),
            clear_next_retry_time=True,
        )
        raise ValueError(error_msg)

    # Purchase 事件必须提供 conversion_id
    if event == "Purchase" and not conversion_id:
        await _mark_failed_and_raise("Purchase 事件必须提供 conversion_id 参数")

    # Purchase 事件必须提供 amount
    if event == "Purchase" and amount is None:
        await _mark_failed_and_raise("Purchase 事件必须提供 amount 参数")

    # 对用户字段改为“软校验”：允许继续上报，但记录缺失字段用于排障
    if event in ("ViewContent", "Purchase"):
        missing_fields = []
        if not email:
            missing_fields.append("email")
        if not phone:
            missing_fields.append("phone")
        if not ip:
            missing_fields.append("ip")
        if not ua:
            missing_fields.append("ua")
        if missing_fields:
            logger.warning(
                f"[第三方上报] {event} 事件字段不完整，仍尝试上报: "
                f"report_log_id={report_log_id}, missing_fields={missing_fields}"
            )

    # Purchase 与 ViewContent 只有在作用域可证明时才允许关联。
    if event == "Purchase" and conversion_id:
        await _link_purchase_to_view_content(
            source=source,
            adsid=adsid,
            conversion_id=conversion_id,
            report_log_id=report_log_id,
            destination_pixel_id=pixel_id,
            identity_scope="platform_scoped" if using_existing_report_log else "unscoped",
            platform=platform,
        )

    logger.info("[第三方上报] 使用像素配置 - Pixel ID: %s, API 版本：%s", pixel_id, api_version)
    
    for attempt in range(hash_attempts):
        try:
            # 使用 Facebook Graph API
            url = f"https://graph.facebook.com/{api_version}/{pixel_id}/events"
            params = {
                "access_token": access_token
            }

            # 直接使用事件类型
            fb_event_name = event

            # 构建事件数据
            # 使用click_time作为event_time（如果提供），否则使用当前时间戳
            if click_time:
                event_time = int(click_time.timestamp())
            else:
                event_time = int(time.time())

            # fbc 中段时间必须与 fbclid 产生时的点击时间一致（秒级 Unix 时间戳）。
            # 若误用「发送请求时的 time.time()」而 event_time 仍为点击时间，会出现
            # event_time < fbc 内嵌时间，Meta 侧常表现为无法归因或报表中不可见。
            fbc_ts = int(click_time.timestamp()) if click_time else event_time

            # 构建用户数据
            user_data = {}
            if use_hash:
                if email:
                    user_data["em"] = sha256_hash(email)
                if phone:
                    user_data["ph"] = sha256_hash(phone)
            else:
                if email:
                    user_data["em"] = email
                if phone:
                    user_data["ph"] = phone
            if ip:
                user_data["client_ip_address"] = ip
            if ua:
                user_data["client_user_agent"] = ua

            if adsid:
                user_data["fbc"] = f"fb.1.{fbc_ts}.{adsid}"
            event_data = {
                "event_name": fb_event_name,
                "event_time": event_time,
                "action_source": "website",
                "event_id": event_key,  # 同一业务事件的重试必须复用稳定 event_id
                "user_data": user_data
            }

            # 购物事件必须添加 custom_data（Meta 要求 value + currency）
            if fb_event_name == "Purchase" and amount is not None:
                event_data["custom_data"] = {
                    "currency": (currency or "USD"),
                    "value": float(amount),
                }

            # 构建请求数据
            send_data = {
                "data": [event_data]
            }

            # 存储完整上报参数
            report_params_json = json.dumps(send_data, ensure_ascii=False)
            attempt_persisted = await update_owned_report_log(
                report_log_id,
                report_params=report_params_json,
                attempt_count=base_attempt_count + attempt + 1,
            )
            if attempt_persisted is False:
                # 不能在累计尝试次数未持久化时发起外部请求，否则故障重试可能突破预算。
                logger.warning(
                    "[第三方上报] 尝试次数持久化失败，暂停本轮发送：report_log_id=%s",
                    report_log_id,
                )
                return {
                    "success": False,
                    "retryable": True,
                    "reason": "attempt_state_persist_failed",
                    "report_log_id": report_log_id,
                }

            logger.info(
                "[第三方上报] 开始发送 (尝试 %s/%s): report_log_id=%s event=%s use_hash=%s",
                attempt + 1, hash_attempts, report_log_id, event, use_hash,
            )
            if use_hash and (email or phone):
                logger.debug(
                    "[第三方上报] 哈希摘要: email_hash=%s, phone_hash=%s",
                    mask_hash_prefix(sha256_hash(email)),
                    mask_hash_prefix(sha256_hash(phone)),
                )

            # 增加超时时间，应对网络延迟
            if not await renew_owned_report_lease():
                logger.warning(
                    "[第三方上报] 发送前租约校验失败，禁止发起外部请求：report_log_id=%s",
                    report_log_id,
                )
                return {
                    "success": False,
                    "retryable": True,
                    "reason": "report_lease_lost_before_send",
                    "report_log_id": report_log_id,
                }
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await _post_with_total_deadline(client, url, json=send_data, params=params)
                # 第三方响应可能回显 user_data；日志只记录状态，不记录响应正文。
                logger.debug("[第三方上报] 响应状态: status=%s", response.status_code)

                if response.status_code == 200:
                    try:
                        response_json = response.json()
                        if response_json.get("events_received"):
                            log_id = response_json.get("fbtrace_id", "")
                            report_success_time = get_app_now_naive()
                            logger.info(
                                "[第三方上报] report_log_id=%s 成功 (尝试 %s/%s), fbtrace_id=%s",
                                report_log_id, attempt + 1, hash_attempts, log_id,
                            )
                            
                            success_persisted = await update_owned_report_log(
                                report_log_id,
                                status="success",
                                response_status=response.status_code,
                                response_body=None,
                                log_id_from_response=log_id,
                                report_success_time=report_success_time,
                                completed_at=report_success_time,
                                clear_next_retry_time=True,
                            )
                            if not success_persisted:
                                logger.warning(
                                    "[第三方上报] 第三方已接收事件，但当前 Worker 租约已失效：report_log_id=%s",
                                    report_log_id,
                                )
                                return {
                                    "success": False,
                                    "retryable": True,
                                    "reason": "report_lease_lost_after_send",
                                    "report_log_id": report_log_id,
                                }
                            
                            # 当Purchase事件上报成功时，发送Telegram通知
                            if fb_event_name == "Purchase":
                                notification_message = f"💰 Purchase事件上报成功！\n"
                                notification_message += f"上报日志ID: {report_log_id}\n"
                                if amount:
                                    notification_message += f"金额: {amount} {currency if currency else ''}\n"
                                notification_message += f"时间: {report_success_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                notification_message += f"跟踪ID: {log_id}"
                                
                                # 发送Telegram通知
                                if settings.TELEGRAM_ADMIN:
                                    # 通知失败不能反向改变已经成功的第三方上报结果，
                                    # 更不能因此重新发送同一笔 Purchase 事件。
                                    try:
                                        await send_telegram_message(
                                            settings.TELEGRAM_ADMIN,
                                            notification_message,
                                        )
                                    except Exception as notify_err:
                                        logger.warning(
                                            "[第三方上报] Purchase 已成功，但 Telegram 通知失败：%s",
                                            type(notify_err).__name__,
                                        )
                                else:
                                    logger.warning("TELEGRAM_ADMIN 未配置，无法发送 Purchase 事件通知")
                            
                            return
                        else:
                            error_msg = "第三方未确认接收事件"
                            failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
                            logger.warning(
                                f"[第三方上报] ✗ 失败 (尝试 {attempt + 1}/{hash_attempts}): {error_msg}")
                            await update_owned_report_log(
                                report_log_id,
                                response_status=response.status_code,
                                response_body=None
                            )
                    except Exception:
                        error_msg = "第三方响应 JSON 解析失败"
                        failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
                        logger.warning(
                            f"[第三方上报] ✗ 失败 (尝试 {attempt + 1}/{hash_attempts}): {error_msg}")
                        await update_owned_report_log(
                            report_log_id,
                            response_status=response.status_code,
                            response_body=None
                        )
                else:
                    error_msg = f"第三方返回 HTTP {response.status_code}"
                    failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
                    logger.warning(
                        f"[第三方上报] ✗ 失败 (尝试 {attempt + 1}/{hash_attempts}): {error_msg}")
                    await update_owned_report_log(
                        report_log_id,
                        response_status=response.status_code,
                        response_body=None
                    )

        except (httpx.TimeoutException, asyncio.TimeoutError):
            error_msg = "请求超时"
            failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
            logger.warning(f"[第三方上报] ✗ 超时 (尝试 {attempt + 1}/{hash_attempts})")
        except httpx.ConnectError:
            error_msg = "连接失败"
            failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
            logger.warning(f"[第三方上报] ✗ 连接失败 (尝试 {attempt + 1}/{hash_attempts})")
        except Exception as e:
            error_msg = f"请求异常（{type(e).__name__}）"
            failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
            logger.warning("[第三方上报] 请求异常（尝试 %s/%s）：%s", attempt + 1, hash_attempts, type(e).__name__)

        # 指数退避策略
        if attempt < hash_attempts - 1:
            delay = base_delay * (2 ** attempt)
            logger.debug("[第三方上报] 等待 %s 秒后重试...", delay)
            await asyncio.sleep(delay)

    # 构建失败原因字符串
    failure_reasons_str = "\n" + "\n".join(failure_reasons) if failure_reasons else "\n无详细信息"
    
    # 如果使用哈希失败，尝试一次不使用哈希
    if fallback_allowed:
        logger.warning(f"[第三方上报] 所有哈希尝试失败，尝试一次不使用哈希...")
        try:
            # 使用 Facebook Graph API（使用自定义或全局配置）
            url = f"https://graph.facebook.com/{api_version}/{pixel_id}/events"
            params = {
                "access_token": access_token
            }
            
            # 构建用户数据（不使用哈希）
            user_data = {}
            if email:
                user_data["em"] = email
            if phone:
                user_data["ph"] = phone
            if ip:
                user_data["client_ip_address"] = ip
            if ua:
                user_data["client_user_agent"] = ua

            # 直接使用事件类型
            fb_event_name = event

            # 构建事件数据
            # 使用click_time作为event_time（如果提供），否则使用当前时间戳
            if click_time:
                event_time = int(click_time.timestamp())
            else:
                event_time = int(time.time())
            fbc_ts = int(click_time.timestamp()) if click_time else event_time
            if adsid:
                user_data["fbc"] = f"fb.1.{fbc_ts}.{adsid}"
            event_data = {
                "event_name": fb_event_name,
                "event_time": event_time,
                "action_source": "website",
                "event_id": event_key,
                "user_data": user_data
            }

            # 购物事件必须添加 custom_data（Meta 要求 value + currency）
            if fb_event_name == "Purchase" and amount is not None:
                event_data["custom_data"] = {
                    "currency": (currency or "USD"),
                    "value": float(amount),
                }

            # 构建请求数据
            send_data = {
                "data": [event_data],
                "test": False
            }

            # 存储完整上报参数
            report_params_json = json.dumps(send_data, ensure_ascii=False)
            attempt_persisted = await update_owned_report_log(
                report_log_id,
                report_params=report_params_json,
                attempt_count=base_attempt_count + hash_attempts + 1,
            )
            if attempt_persisted is False:
                logger.warning(
                    "[第三方上报] 非哈希兜底尝试次数持久化失败，暂停发送：report_log_id=%s",
                    report_log_id,
                )
                return {
                    "success": False,
                    "retryable": True,
                    "reason": "attempt_state_persist_failed",
                    "report_log_id": report_log_id,
                }

            logger.info(
                "[第三方上报] 开始发送 (尝试 %s/%s - 不使用哈希): report_log_id=%s event=%s",
                hash_attempts + 1, hash_attempts + 1, report_log_id, event,
            )

            # 增加超时时间，应对网络延迟
            if not await renew_owned_report_lease():
                logger.warning(
                    "[第三方上报] 发送前租约校验失败，禁止发起外部请求：report_log_id=%s",
                    report_log_id,
                )
                return {
                    "success": False,
                    "retryable": True,
                    "reason": "report_lease_lost_before_send",
                    "report_log_id": report_log_id,
                }
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await _post_with_total_deadline(client, url, json=send_data, params=params)
                # 第三方响应可能回显 user_data；日志只记录状态，不记录响应正文。
                logger.debug("[第三方上报] 响应状态: status=%s", response.status_code)

                if response.status_code == 200:
                    try:
                        response_json = response.json()
                        if response_json.get("events_received"):
                            log_id = response_json.get("fbtrace_id", "")
                            report_success_time = get_app_now_naive()
                            logger.info(
                                "[第三方上报] report_log_id=%s 成功 (尝试 %s/%s - 不使用哈希), fbtrace_id=%s",
                                report_log_id, hash_attempts + 1, hash_attempts + 1, log_id,
                            )
                            
                            success_persisted = await update_owned_report_log(
                                report_log_id,
                                status="success",
                                response_status=response.status_code,
                                response_body=None,
                                log_id_from_response=log_id,
                                report_success_time=report_success_time,
                                completed_at=report_success_time,
                                clear_next_retry_time=True,
                            )
                            if not success_persisted:
                                logger.warning(
                                    "[第三方上报] 第三方已接收事件，但当前 Worker 租约已失效：report_log_id=%s",
                                    report_log_id,
                                )
                                return {
                                    "success": False,
                                    "retryable": True,
                                    "reason": "report_lease_lost_after_send",
                                    "report_log_id": report_log_id,
                                }
                            return
                        else:
                            error_msg = "第三方未确认接收事件"
                            failure_reasons.append(f"尝试 {hash_attempts + 1} (不使用哈希): {error_msg}")
                            logger.warning(
                                f"[第三方上报] ✗ 失败 (尝试 {hash_attempts + 1}/{hash_attempts + 1} - 不使用哈希): {error_msg}")
                            await update_owned_report_log(
                                report_log_id,
                                response_status=response.status_code,
                                response_body=None
                            )
                    except Exception:
                        error_msg = "第三方响应 JSON 解析失败"
                        failure_reasons.append(f"尝试 {hash_attempts + 1} (不使用哈希): {error_msg}")
                        logger.warning(
                            f"[第三方上报] ✗ 失败 (尝试 {hash_attempts + 1}/{hash_attempts + 1} - 不使用哈希): {error_msg}")
                        await update_owned_report_log(
                            report_log_id,
                            response_status=response.status_code,
                            response_body=None
                        )
                else:
                    error_msg = f"第三方返回 HTTP {response.status_code}"
                    failure_reasons.append(f"尝试 {hash_attempts + 1} (不使用哈希): {error_msg}")
                    logger.warning(
                        f"[第三方上报] ✗ 失败 (尝试 {hash_attempts + 1}/{hash_attempts + 1} - 不使用哈希): {error_msg}")
                    await update_owned_report_log(
                        report_log_id,
                        response_status=response.status_code,
                        response_body=None
                    )

        except (httpx.TimeoutException, asyncio.TimeoutError):
            error_msg = "请求超时"
            failure_reasons.append(f"尝试 {hash_attempts + 1} (不使用哈希): {error_msg}")
            logger.warning(f"[第三方上报] ✗ 超时 (尝试 {hash_attempts + 1}/{hash_attempts + 1} - 不使用哈希)")
        except httpx.ConnectError:
            error_msg = "连接失败"
            failure_reasons.append(f"尝试 {hash_attempts + 1} (不使用哈希): {error_msg}")
            logger.warning(f"[第三方上报] ✗ 连接失败 (尝试 {hash_attempts + 1}/{hash_attempts + 1} - 不使用哈希)")
        except Exception as e:
            error_msg = f"请求异常（{type(e).__name__}）"
            failure_reasons.append(f"尝试 {hash_attempts + 1} (不使用哈希): {error_msg}")
            logger.warning("[第三方上报] 请求异常（不使用哈希）：%s", type(e).__name__)

    # 更新失败原因字符串
    failure_reasons_str = "\n" + "\n".join(failure_reasons) if failure_reasons else "\n无详细信息"
    logger.error(
        "[第三方上报] 全部尝试失败：report_log_id=%s event=%s attempts=%s",
        report_log_id, event, len(failure_reasons),
    )

    # 失败后释放发送租约；按累计尝试次数安排退避，达到预算后转为人工重试。
    final_attempt_count = base_attempt_count + (hash_attempts + (1 if fallback_allowed else 0))
    retry_at = None
    if final_attempt_count < max_attempts_total:
        retry_delay_minutes = min(5 * (2 ** (base_attempt_count // 4)), 60)
        retry_at = get_app_now_naive() + timedelta(minutes=retry_delay_minutes)
    finalized = await update_owned_report_log(
        report_log_id,
        status="failed",
        attempt_count=final_attempt_count,
        error_message=failure_reasons_str.strip(),
        report_start_time=get_app_now_naive() - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1),
        completed_at=get_app_now_naive(),
        next_retry_time=retry_at,
        clear_next_retry_time=retry_at is None,
    )
    if not finalized:
        logger.warning(
            "[第三方上报] 当前 Worker 租约已失效，跳过过期失败结果写入：report_log_id=%s",
            report_log_id,
        )
        return {
            "success": False,
            "retryable": True,
            "reason": "report_lease_lost",
            "report_log_id": report_log_id,
        }

    # 发送告警
    try:
        await send_telegram_message(
            settings.TELEGRAM_ADMIN,
            f"⚠️ 第三方上报失败\n\n"
            f"日志ID: {report_log_id}\n"
            f"事件类型: {event}\n"
            f"尝试次数: {final_attempt_count}\n"
            f"失败原因:{failure_reasons_str}\n"
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        logger.info("[第三方上报] 告警已发送")
    except Exception as notify_err:
        logger.warning("[第三方上报] 发送告警失败：%s", type(notify_err).__name__)


def is_outbox_payload_editable(report_log, now: Optional[datetime] = None) -> bool:
    """只有尚未尝试发送、失败且租约已释放的 Outbox 才允许修正发送载荷。"""
    if not getattr(report_log, "outbox_enqueued", False):
        return False
    if getattr(report_log, "pii_scrubbed_at", None) is not None:
        return False
    if getattr(report_log, "status", None) != "failed":
        return False
    if int(getattr(report_log, "attempt_count", 0) or 0) > 0:
        return False
    now = now or get_app_now_naive()
    stale_lease_time = now - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1)
    report_start_time = getattr(report_log, "report_start_time", None)
    return report_start_time is None or report_start_time < stale_lease_time


async def retry_report_log(log_id: int):
    """
    将失败的持久化 Outbox 事件重新排队。

    不在请求进程中创建非持久化 asyncio task，也不从日志读取旧凭据；
    worker 在实际发送时按短链/斗篷配置引用解析当前有效凭据。
    非 Outbox 日志缺少可靠配置引用，拒绝伪装成可重试成功。
    """
    now = get_app_now_naive()
    stale_lease_time = now - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(ThirdPartyReportLog)
                .where(
                    ThirdPartyReportLog.id == log_id,
                    ThirdPartyReportLog.outbox_enqueued.is_(True),
                    ThirdPartyReportLog.identity_scope == "platform_scoped",
                    ThirdPartyReportLog.platform.is_not(None),
                    ThirdPartyReportLog.platform != "",
                    ThirdPartyReportLog.status == "failed",
                    ThirdPartyReportLog.pii_scrubbed_at.is_(None),
                    or_(
                        ThirdPartyReportLog.error_message.is_(None),
                        ThirdPartyReportLog.error_message != "短链接已删除，无法解析像素配置",
                    ),
                    or_(
                        ThirdPartyReportLog.short_link_id.is_not(None),
                        (
                            ThirdPartyReportLog.cloak_name.is_not(None)
                            & ThirdPartyReportLog.short_code.is_not(None)
                        ),
                    ),
                    or_(
                        ThirdPartyReportLog.report_start_time.is_(None),
                        ThirdPartyReportLog.report_start_time < stale_lease_time,
                    ),
                )
                .values(
                    status="pending",
                    attempt_count=0,
                    response_status=None,
                    response_body=None,
                    log_id=None,
                    error_message=None,
                    report_start_time=stale_lease_time,
                    report_success_time=None,
                    completed_at=None,
                    next_retry_time=now,
                )
            )
            await db.commit()
            if (result.rowcount or 0) != 1:
                logger.info(
                    "[第三方上报] 重试未入队：日志不存在、非 Outbox、非失败状态或租约仍有效: id=%s",
                    log_id,
                )
                return False
            logger.info("[第三方上报] Outbox 事件已重新排队，等待持久化 worker：id=%s", log_id)
            return True
    except Exception as exc:
        logger.warning("[第三方上报] Outbox 重试入队失败：id=%s error_type=%s", log_id, type(exc).__name__)
        return False


async def update_report_log_params(
        log_id: int,
        adsid: Optional[str] = None,
        event: Optional[str] = None,
        conversion_id: Optional[str] = None,
        email: Optional[str] = None,
        ip: Optional[str] = None,
        phone: Optional[str] = None,
        ua: Optional[str] = None,
        currency: Optional[str] = None,
        amount: Optional[float] = None,
        report_params: Optional[str] = None,
        use_hash: Optional[bool] = None
):
    """更新日志参数；身份字段变更必须先取得旧/新基础身份锁并检查冲突。"""
    try:
        async with AsyncSessionLocal() as db:
            # 先读取快照但不持有行锁；身份锁必须先于日志行锁，避免与创建路径反向死锁。
            snapshot_result = await db.execute(
                select(ThirdPartyReportLog)
                .where(ThirdPartyReportLog.id == log_id)
                .limit(1)
            )
            snapshot = snapshot_result.scalars().first()
            if snapshot is None:
                logger.warning("[第三方上报] 日志记录不存在: id=%s", log_id)
                return False
            if getattr(snapshot, "pii_scrubbed_at", None) is not None:
                logger.warning("[第三方上报] 已清理个人信息的日志不可重新写入载荷: id=%s", log_id)
                return False

            identity_changed = (
                (adsid is not None and adsid != snapshot.adsid)
                or (event is not None and event != snapshot.event)
                or (conversion_id is not None and conversion_id != snapshot.conversion_id)
            )
            identity_scope = getattr(snapshot, "identity_scope", "legacy_unresolved")
            if identity_scope not in {"unscoped", "platform_scoped", "legacy_unresolved"}:
                return False
            if identity_changed and identity_scope != "unscoped":
                logger.warning(
                    "[第三方上报] 仅允许未入队 unscoped 日志修正事件身份: id=%s",
                    log_id,
                )
                return False
            if identity_changed:
                # 直接发送日志一旦开始尝试，就成为外部事件身份的审计证据；
                # 不允许管理员改写已尝试/成功/已完成事件的幂等身份。
                now = get_app_now_naive()
                report_start_time = getattr(snapshot, "report_start_time", None)
                active_lease = bool(
                    report_start_time
                    and report_start_time
                    >= now - timedelta(seconds=REPORT_LOG_LEASE_SECONDS)
                )
                if (
                    int(getattr(snapshot, "attempt_count", 0) or 0) > 0
                    or getattr(snapshot, "status", None) == "success"
                    or getattr(snapshot, "report_success_time", None) is not None
                    or getattr(snapshot, "completed_at", None) is not None
                    or active_lease
                ):
                    logger.warning(
                        "[第三方上报] 已尝试、已完成或租约有效的事件身份不可修改: id=%s",
                        log_id,
                    )
                    return False
            if identity_scope == "platform_scoped" and not getattr(snapshot, "platform", None):
                logger.warning("[第三方上报] 平台作用域日志缺少平台标识: id=%s", log_id)
                return False
            if identity_scope == "unscoped" and (
                getattr(snapshot, "platform", None) is not None
                or getattr(snapshot, "outbox_enqueued", False)
            ):
                logger.warning("[第三方上报] unscoped 日志作用域字段不一致: id=%s", log_id)
                return False
            if getattr(snapshot, "outbox_enqueued", False) and identity_changed:
                return False

            if identity_changed:
                old_identity = (
                    snapshot.source,
                    snapshot.adsid,
                    snapshot.event,
                    snapshot.conversion_id,
                )
                new_identity = (
                    snapshot.source,
                    adsid if adsid is not None else snapshot.adsid,
                    event if event is not None else snapshot.event,
                    conversion_id if conversion_id is not None else snapshot.conversion_id,
                )
                # 两把锁按稳定 hash 顺序获取，避免 A->B 与 B->A 管理编辑互相死锁。
                ordered_identities = sorted(
                    {old_identity, new_identity},
                    key=lambda parts: hashlib.sha256(
                        _report_base_identity_value(*parts).encode("utf-8")
                    ).hexdigest(),
                )
                for source_value, adsid_value, event_value, conversion_value in ordered_identities:
                    await _lock_report_base_identity(
                        db,
                        source=source_value,
                        adsid=adsid_value,
                        event=event_value,
                        conversion_id=conversion_value,
                    )

                # 管理编辑同样必须尊重历史未解析身份门禁。旧平台归属不能
                # 根据本次编辑内容推断，否则可绕过创建入口的 fail-closed 保护。
                if await _has_legacy_unresolved_base_identity(
                    db,
                    source=new_identity[0],
                    adsid=new_identity[1],
                    event=new_identity[2],
                    conversion_id=new_identity[3],
                ):
                    logger.warning(
                        "[第三方上报] 管理编辑目标身份存在平台归属未确认的历史事件，拒绝修改: id=%s",
                        log_id,
                    )
                    return False

            # 取得身份锁后再锁定目标行，并确认快照身份没有被并发管理员操作改写。
            result = await db.execute(
                select(ThirdPartyReportLog)
                .where(ThirdPartyReportLog.id == log_id)
                .with_for_update()
            )
            log_entry = result.scalars().first()
            if log_entry is None:
                return False
            snapshot_identity = (
                snapshot.source, snapshot.adsid, snapshot.event, snapshot.conversion_id
            )
            current_identity = (
                log_entry.source, log_entry.adsid, log_entry.event, log_entry.conversion_id
            )
            if current_identity != snapshot_identity:
                logger.warning("[第三方上报] 管理编辑期间事件身份已变化，请刷新后重试: id=%s", log_id)
                return False
            if getattr(log_entry, "pii_scrubbed_at", None) is not None:
                return False

            if identity_changed:
                new_adsid = adsid if adsid is not None else log_entry.adsid
                new_event = event if event is not None else log_entry.event
                new_conversion_id = (
                    conversion_id if conversion_id is not None else log_entry.conversion_id
                )
                target_event_key = build_event_idempotency_key(
                    log_entry.source,
                    new_adsid,
                    new_event,
                    new_conversion_id,
                )
                duplicate_result = await db.execute(
                    select(ThirdPartyReportLog.id)
                    .where(
                        ThirdPartyReportLog.event_key == target_event_key,
                        ThirdPartyReportLog.id != log_id,
                    )
                    .limit(1)
                )
                if duplicate_result.scalars().first() is not None:
                    logger.warning("[第三方上报] 管理编辑目标事件键已被占用，拒绝修改: id=%s", log_id)
                    return False

                scoped_query = select(ThirdPartyReportLog.id).where(
                    ThirdPartyReportLog.source == log_entry.source,
                    ThirdPartyReportLog.adsid == new_adsid,
                    ThirdPartyReportLog.event == new_event,
                    ThirdPartyReportLog.identity_scope == "platform_scoped",
                )
                if new_event != "ViewContent":
                    scoped_query = scoped_query.where(
                        ThirdPartyReportLog.conversion_id == new_conversion_id
                    )
                scoped_result = await db.execute(scoped_query.limit(1))
                if scoped_result.scalars().first() is not None:
                    logger.warning("[第三方上报] 管理编辑目标身份已属于平台作用域事件，拒绝修改")
                    return False

            payload_updates_requested = any(value is not None for value in (
                email, ip, phone, ua, currency, amount, report_params, use_hash
            ))
            if (
                log_entry.outbox_enqueued
                and payload_updates_requested
                and not is_outbox_payload_editable(log_entry)
            ):
                logger.warning(
                    "[第三方上报] 已开始发送或已完成的 Outbox 载荷不可修改: id=%s attempts=%s status=%s",
                    log_id,
                    log_entry.attempt_count,
                    log_entry.status,
                )
                return False

            if adsid is not None:
                log_entry.adsid = adsid
            if event is not None:
                log_entry.event = event
            if conversion_id is not None:
                log_entry.conversion_id = conversion_id
            if identity_changed:
                log_entry.event_key = build_event_idempotency_key(
                    log_entry.source,
                    log_entry.adsid,
                    log_entry.event,
                    log_entry.conversion_id,
                )
            if email is not None:
                log_entry.email = email
            if ip is not None:
                log_entry.ip = ip
            if phone is not None:
                log_entry.phone = phone
            if ua is not None:
                log_entry.ua = ua
            if currency is not None:
                log_entry.currency = currency
            if amount is not None:
                log_entry.amount = amount
            if report_params is not None:
                log_entry.report_params = report_params
            if use_hash is not None:
                log_entry.use_hash = use_hash

            await db.commit()
            logger.info("[第三方上报] 已更新日志参数: id=%s", log_id)
            return True

    except Exception as exc:
        logger.warning("[第三方上报] 更新日志参数失败：%s", type(exc).__name__)
        return False

