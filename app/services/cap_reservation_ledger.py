"""
Cap Reservation 独立持久化账本服务。

账本写入使用独立 AsyncSessionLocal，不加入 Postback 主业务事务。
prepare_and_claim() 使用数据库行锁与租约，防止同一事件的并发 Postback
同时操作同一个稳定 Redis token。
"""
import hashlib
import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.core.cap.redis_counter import RedisCapManager, get_daily_cap_key, get_total_cap_key
from app.models.cap_reservation import CapReservation

logger = logging.getLogger(__name__)

ACTIVE_STATES = ("PREPARED", "RESERVED", "NEEDS_RECONCILIATION")
FINAL_STATES = ("COMMITTED", "ROLLED_BACK")
DEFAULT_LEASE_SECONDS = 300


def normalize_event_name(event_name: Optional[str]) -> str:
    """统一正式事件名，避免 None、空串和空白串生成不同幂等键。"""
    return (event_name or "").strip() or "default"


def build_reservation_identity(
    *,
    platform: str,
    conversion_id: str,
    event_name: Optional[str],
    offer_id: int,
    publisher_id: Optional[int],
    cap_kind: str,
    business_date: Optional[date],
) -> dict:
    """生成稳定、无歧义的事件 + Redis scope 身份。"""
    normalized_kind = (cap_kind or "").strip().lower()
    if normalized_kind not in {"daily", "total"}:
        raise ValueError("cap_kind 必须为 daily 或 total")
    if not platform or not platform.strip():
        raise ValueError("platform 不能为空")
    if conversion_id is None or not str(conversion_id).strip():
        raise ValueError("conversion_id 不能为空")
    if not isinstance(offer_id, int) or offer_id <= 0:
        raise ValueError("offer_id 必须为正整数")
    if publisher_id is not None and int(publisher_id) <= 0:
        raise ValueError("publisher_id 必须为正整数或 NULL")
    if normalized_kind == "daily" and business_date is None:
        raise ValueError("Daily Reservation 必须提供 business_date")
    if normalized_kind == "total" and business_date is not None:
        raise ValueError("Total Reservation 的 business_date 必须为 NULL")

    scope = {
        "platform": platform.strip(),
        "conversion_id": str(conversion_id).strip(),
        "event_name": normalize_event_name(event_name),
        "offer_id": offer_id,
        "publisher_scope": "global" if publisher_id is None else f"publisher:{int(publisher_id)}",
        "cap_kind": normalized_kind,
        "business_date": business_date.isoformat() if business_date else "total",
    }
    encoded = json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    reservation_key = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return {"reservation_key": reservation_key, **scope}


class CapReservationLedger:
    """独立数据库会话上的账本写入与状态机。"""

    @staticmethod
    async def prepare_and_claim(
        *,
        platform: str,
        conversion_id: str,
        event_name: Optional[str],
        offer_id: int,
        publisher_id: Optional[int],
        cap_kind: str,
        business_date: Optional[date],
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> tuple[CapReservation, bool, Optional[str]]:
        """
        独立提交 PREPARED 并领取短租约。

        返回 (row, claimed, lease_owner)。claimed=False 表示同一事件已在处理、
        已提交或需要人工/恢复 Worker 对账；调用方必须拒绝继续操作 Redis。
        """
        if lease_seconds < 30 or lease_seconds > 3600:
            raise ValueError("Reservation lease_seconds 必须在 30 到 3600 秒之间")
        identity = build_reservation_identity(
            platform=platform,
            conversion_id=conversion_id,
            event_name=event_name,
            offer_id=offer_id,
            publisher_id=publisher_id,
            cap_kind=cap_kind,
            business_date=business_date,
        )
        now = get_app_now_naive()
        owner = uuid.uuid4().hex
        expires = now + timedelta(seconds=lease_seconds)
        kind = identity["cap_kind"]
        if kind == "daily":
            counter_key = get_daily_cap_key(
                offer_id, datetime.combine(business_date, datetime.min.time()), publisher_id
            )
        else:
            counter_key = get_total_cap_key(offer_id, publisher_id)
        token_key = f"{counter_key}:reservation:{identity['reservation_key']}"

        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(CapReservation)
                .where(CapReservation.reservation_key == identity["reservation_key"])
                .with_for_update()
            )
            if row is None:
                row = CapReservation(
                    reservation_key=identity["reservation_key"],
                    platform=identity["platform"],
                    conversion_id=identity["conversion_id"],
                    event_name=identity["event_name"],
                    offer_id=offer_id,
                    publisher_id=publisher_id,
                    cap_kind=kind,
                    business_date=business_date,
                    redis_counter_key=counter_key,
                    redis_token_key=token_key,
                    redis_reserved=False,
                    state="PREPARED",
                    lease_owner=owner,
                    lease_expires_at=expires,
                    prepared_at=now,
                )
                session.add(row)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    # 唯一键竞争时重新读取并走同一行锁/租约判断，不盲目继续 Redis 操作。
                    async with AsyncSessionLocal() as retry_session:
                        winner = await retry_session.scalar(
                            select(CapReservation)
                            .where(CapReservation.reservation_key == identity["reservation_key"])
                            .with_for_update()
                        )
                        if winner is None:
                            raise
                        return await CapReservationLedger._claim_existing(
                            retry_session, winner, owner, now, expires
                        )
                await session.refresh(row)
                return row, True, owner

            return await CapReservationLedger._claim_existing(
                session, row, owner, now, expires
            )

    @staticmethod
    async def _claim_existing(session, row, owner, now, expires):
        """仅允许租约过期的可恢复状态被新请求接管。"""
        if row.state == "COMMITTED":
            await session.commit()
            return row, False, None
        if row.state == "NEEDS_RECONCILIATION":
            await session.commit()
            return row, False, None
        if row.state not in {"PREPARED", "RESERVED", "ROLLED_BACK"}:
            await session.commit()
            raise RuntimeError(f"未知 Cap Reservation 状态，拒绝继续：{row.state}")
        if (
            row.state != "ROLLED_BACK"
            and row.lease_owner
            and row.lease_expires_at
            and row.lease_expires_at > now
        ):
            await session.commit()
            return row, False, None

        if row.state == "ROLLED_BACK":
            row.state = "PREPARED"
            row.redis_reserved = False
            row.redis_token_cleaned = False
            row.prepared_at = now
            row.reserved_at = None
            row.finalized_at = None
            row.last_error = None
        row.lease_owner = owner
        row.lease_expires_at = expires
        row.attempts = int(row.attempts or 0) + 1
        row.updated_at = now
        await session.commit()
        await session.refresh(row)
        return row, True, owner

    @staticmethod
    async def mark_reserved(reservation_key: str, lease_owner: str) -> None:
        """Redis Lua 明确返回预留成功后，独立提交 RESERVED。"""
        now = get_app_now_naive()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(CapReservation)
                .where(
                    CapReservation.reservation_key == reservation_key,
                    CapReservation.state.in_(("PREPARED", "RESERVED")),
                    CapReservation.lease_owner == lease_owner,
                )
                .values(
                    state="RESERVED",
                    redis_reserved=True,
                    reserved_at=now,
                    lease_expires_at=now + timedelta(seconds=DEFAULT_LEASE_SECONDS),
                    updated_at=now,
                    last_error=None,
                )
            )
            await session.commit()
            if result.rowcount != 1:
                current = await session.execute(
                    select(CapReservation.state, CapReservation.lease_owner).where(
                        CapReservation.reservation_key == reservation_key
                    )
                )
                current_state, current_owner = current.one_or_none() or (None, None)
                if current_state != "RESERVED" or current_owner != lease_owner:
                    raise RuntimeError(
                        f"Cap Reservation 状态转换/租约校验失败：state={current_state}, owner_matches={current_owner == lease_owner}"
                    )

    @staticmethod
    async def renew_lease(
        reservation_key: str,
        lease_owner: str,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> None:
        """在 Postback 主事务提交前续租，防止恢复 Worker 与仍在执行的请求竞争。"""
        if lease_seconds < 30 or lease_seconds > 3600:
            raise ValueError("Reservation lease_seconds 必须在 30 到 3600 秒之间")
        now = get_app_now_naive()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(CapReservation)
                .where(
                    CapReservation.reservation_key == reservation_key,
                    CapReservation.state.in_(("PREPARED", "RESERVED")),
                    CapReservation.lease_owner == lease_owner,
                )
                .values(
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    updated_at=now,
                )
            )
            await session.commit()
            if result.rowcount != 1:
                raise RuntimeError(
                    f"Cap Reservation lease 续租失败，拒绝提交业务事务：{reservation_key}"
                )

    @staticmethod
    async def finalize(
        reservation_key: str,
        state: str,
        *,
        lease_owner: Optional[str] = None,
    ) -> None:
        """提交账本终态；Redis token 清理失败单独记录并交由恢复任务重试。"""
        if state not in FINAL_STATES:
            raise ValueError(f"非法 Cap Reservation 终态：{state}")
        now = get_app_now_naive()
        conditions = [
            CapReservation.reservation_key == reservation_key,
            CapReservation.state.in_(ACTIVE_STATES),
        ]
        if lease_owner:
            conditions.append(CapReservation.lease_owner == lease_owner)

        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(CapReservation)
                .where(CapReservation.reservation_key == reservation_key)
                .with_for_update()
            )
            if row is None:
                raise RuntimeError(f"Cap Reservation 不存在：{reservation_key}")

            token_cleaned = state == "ROLLED_BACK"
            if state == "COMMITTED":
                # token 即使在 RESERVED 标记前也可能已由 Lua 创建；终态清理必须覆盖此窗口。
                try:
                    await RedisCapManager.delete_reservation_token(row.redis_token_key)
                    token_cleaned = True
                except Exception:
                    token_cleaned = False
                    logger.critical(
                        "转化已提交，但 Redis Reservation token 尚未清理，将由恢复任务重试：%s",
                        reservation_key,
                        exc_info=True,
                    )

            if row.state == state:
                # 幂等重复终态请求也可补写 token 清理结果。
                if state == "COMMITTED" and token_cleaned:
                    row.redis_token_cleaned = True
                    row.lease_owner = None
                    row.lease_expires_at = None
                    row.updated_at = now
                    await session.commit()
                else:
                    await session.commit()
                return

            result = await session.execute(
                update(CapReservation)
                .where(*conditions)
                .values(
                    state=state,
                    redis_reserved=(False if state == "ROLLED_BACK" else CapReservation.redis_reserved),
                    redis_token_cleaned=token_cleaned,
                    finalized_at=now,
                    updated_at=now,
                    lease_owner=None,
                    lease_expires_at=None,
                    last_error=None if token_cleaned else "Redis token cleanup pending",
                )
            )
            await session.commit()
            if result.rowcount != 1:
                current = await session.scalar(
                    select(CapReservation.state).where(
                        CapReservation.reservation_key == reservation_key
                    )
                )
                if current != state:
                    raise RuntimeError(
                        f"Cap Reservation 终态更新失败：expected={state}, actual={current}"
                    )

    @staticmethod
    async def mark_token_cleaned(
        reservation_key: str,
        lease_owner: str,
    ) -> None:
        """恢复任务成功删除已提交 token 后，确认清理完成并释放租约。"""
        now = get_app_now_naive()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(CapReservation)
                .where(
                    CapReservation.reservation_key == reservation_key,
                    CapReservation.state == "COMMITTED",
                    CapReservation.lease_owner == lease_owner,
                )
                .values(
                    redis_token_cleaned=True,
                    lease_owner=None,
                    lease_expires_at=None,
                    updated_at=now,
                    last_error=None,
                )
            )
            await session.commit()
            if result.rowcount != 1:
                row = await session.scalar(
                    select(CapReservation).where(
                        CapReservation.reservation_key == reservation_key
                    )
                )
                if row is None or row.state != "COMMITTED" or not row.redis_token_cleaned:
                    raise RuntimeError(
                        f"Cap Reservation token 清理状态更新失败：{reservation_key}"
                    )

    @staticmethod
    async def mark_needs_reconciliation(
        reservation_key: str,
        error: str,
        *,
        lease_owner: Optional[str] = None,
    ) -> None:
        """保留无法确定的跨存储状态，绝不擅自删除 token 或扣减计数。"""
        now = get_app_now_naive()
        conditions = [
            CapReservation.reservation_key == reservation_key,
            CapReservation.state.in_(ACTIVE_STATES),
        ]
        if lease_owner:
            conditions.append(CapReservation.lease_owner == lease_owner)
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(CapReservation)
                .where(*conditions)
                .values(
                    state="NEEDS_RECONCILIATION",
                    attempts=CapReservation.attempts + 1,
                    last_error=(error or "unknown")[:8000],
                    updated_at=now,
                    lease_owner=None,
                    lease_expires_at=None,
                )
            )
            await session.commit()
