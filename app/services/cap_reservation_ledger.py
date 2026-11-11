"""
Cap Reservation 独立持久化账本服务。

所有账本写入使用独立 AsyncSessionLocal，不加入 Postback 主业务事务。
此服务仅提供幂等记录与状态转换；Redis 恢复 Worker 和 Postback 全链路接入
必须在后续阶段完成，不能将“有账本表”误认为已经具备自动恢复能力。
"""
import hashlib
import json
import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.models.cap_reservation import CapReservation
from app.core.cap.redis_counter import get_daily_cap_key, get_total_cap_key

logger = logging.getLogger(__name__)

ACTIVE_STATES = ("PREPARED", "RESERVED", "NEEDS_RECONCILIATION")
FINAL_STATES = ("COMMITTED", "ROLLED_BACK")


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
    if normalized_kind == "daily" and business_date is None:
        raise ValueError("Daily Reservation 必须提供 business_date")
    if normalized_kind == "total" and business_date is not None:
        raise ValueError("Total Reservation 的 business_date 必须为 NULL")

    scope = {
        "platform": platform.strip(),
        "conversion_id": str(conversion_id).strip(),
        "event_name": normalize_event_name(event_name),
        "offer_id": offer_id,
        # 明确区分全局 scope 与 publisher id，避免 NULL/数字字符串歧义。
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
    async def prepare(
        *,
        platform: str,
        conversion_id: str,
        event_name: Optional[str],
        offer_id: int,
        publisher_id: Optional[int],
        cap_kind: str,
        business_date: Optional[date],
    ) -> CapReservation:
        identity = build_reservation_identity(
            platform=platform,
            conversion_id=conversion_id,
            event_name=event_name,
            offer_id=offer_id,
            publisher_id=publisher_id,
            cap_kind=cap_kind,
            business_date=business_date,
        )
        if cap_kind.lower() == "daily":
            counter_key = get_daily_cap_key(
                offer_id,
                datetime.combine(business_date, datetime.min.time()),
                publisher_id,
            )
        else:
            counter_key = get_total_cap_key(offer_id, publisher_id)
        token_key = f"{counter_key}:reservation:{identity['reservation_key']}"

        async with AsyncSessionLocal() as session:
            existing = await session.scalar(
                select(CapReservation)
                .where(CapReservation.reservation_key == identity["reservation_key"])
                .with_for_update()
            )
            if existing is not None:
                if existing.state == "ROLLED_BACK":
                    # 同一事件重试：仅在已确认回滚的终态重新打开同一稳定 token。
                    existing.state = "PREPARED"
                    existing.prepared_at = get_app_now_naive()
                    existing.reserved_at = None
                    existing.finalized_at = None
                    existing.last_error = None
                    existing.lease_owner = None
                    existing.lease_expires_at = None
                    await session.commit()
                elif existing.state in ACTIVE_STATES or existing.state == "COMMITTED":
                    return existing
                else:
                    raise RuntimeError(
                        f"未知 Cap Reservation 状态，拒绝覆盖：{existing.state}"
                    )
                return existing

            row = CapReservation(
                reservation_key=identity["reservation_key"],
                platform=identity["platform"],
                conversion_id=identity["conversion_id"],
                event_name=identity["event_name"],
                offer_id=offer_id,
                publisher_id=publisher_id,
                cap_kind=cap_kind.lower(),
                business_date=business_date,
                redis_counter_key=counter_key,
                redis_token_key=token_key,
                state="PREPARED",
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                # 并发请求可能同时首次创建相同稳定键；回滚后读取赢家记录。
                await session.rollback()
                winner = await session.scalar(
                    select(CapReservation).where(
                        CapReservation.reservation_key == identity["reservation_key"]
                    )
                )
                if winner is None:
                    raise
                return winner
            await session.refresh(row)
            return row

    @staticmethod
    async def mark_reserved(reservation_key: str) -> None:
        """Redis Lua 明确返回预留成功后，独立提交 RESERVED。"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(CapReservation)
                .where(
                    CapReservation.reservation_key == reservation_key,
                    CapReservation.state == "PREPARED",
                )
                .values(
                    state="RESERVED",
                    reserved_at=get_app_now_naive(),
                    updated_at=get_app_now_naive(),
                    last_error=None,
                )
            )
            await session.commit()
            if result.rowcount != 1:
                current = await session.scalar(
                    select(CapReservation.state).where(
                        CapReservation.reservation_key == reservation_key
                    )
                )
                if current != "RESERVED":
                    raise RuntimeError(
                        f"Cap Reservation 状态转换 PREPARED->RESERVED 失败：{current}"
                    )

    @staticmethod
    async def finalize(reservation_key: str, state: str) -> None:
        """将账本推进到已确认终态；仅允许 COMMITTED 或 ROLLED_BACK。"""
        if state not in FINAL_STATES:
            raise ValueError(f"非法 Cap Reservation 终态：{state}")
        now = get_app_now_naive()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(CapReservation)
                .where(
                    CapReservation.reservation_key == reservation_key,
                    CapReservation.state.in_(ACTIVE_STATES),
                )
                .values(
                    state=state,
                    finalized_at=now,
                    updated_at=now,
                    lease_owner=None,
                    lease_expires_at=None,
                    last_error=None,
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
    async def mark_needs_reconciliation(
        reservation_key: str,
        error: str,
    ) -> None:
        """保留无法确定的跨存储状态，绝不擅自删除 token 或扣减计数。"""
        now = get_app_now_naive()
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(CapReservation)
                .where(
                    CapReservation.reservation_key == reservation_key,
                    CapReservation.state.in_(ACTIVE_STATES),
                )
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
