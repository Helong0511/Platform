"""
Cap 限制检查器

检查转化是否超过 Cap 限制（Daily Cap / Total Cap）
"""
import logging
from typing import Optional, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cap import check_cap, increment_cap_count, rollback_cap_redis_counts
from app.core.cap.redis_counter import RedisCapManager
from app.core.config import settings
from app.services.cap_reservation_ledger import CapReservationLedger

logger = logging.getLogger(__name__)


class CapChecker:
    """Cap 限制检查器"""
    
    @staticmethod
    async def check(
        offer_id: Optional[int],
        publisher_id: Optional[int],
        advertiser_id: Optional[int],
        db: AsyncSession
    ) -> Tuple[bool, str]:
        """
        检查是否超过 Cap 限制
        
        Args:
            offer_id: Offer ID
            publisher_id: Publisher ID
            advertiser_id: Advertiser ID
            db: 数据库会话
        
        Returns:
            tuple: (是否通过检查，状态消息)
        """
        if not offer_id:
            logger.debug("没有 Offer ID，跳过 Cap 检查")
            return True, "no_offer_id"
        
        try:
            # 检查 Cap 限制
            cap_result, cap_message = await check_cap(
                db=db,
                offer_id=offer_id,
                publisher_id=publisher_id,
                advertiser_id=advertiser_id
            )
            
            if not cap_result:
                logger.warning(
                    f"Cap 限制已超出：offer_id={offer_id}, "
                    f"publisher_id={publisher_id}, message={cap_message}"
                )
                return False, cap_message or "cap_exceeded"
            
            logger.debug(
                f"Cap 检查通过：offer_id={offer_id}, publisher_id={publisher_id}"
            )
            return True, "cap_ok"
            
        except Exception as e:
            logger.error(f"Cap 检查失败：{e}", exc_info=True)
            if settings.CAP_FAIL_OPEN:
                return True, "cap_check_error"
            return False, "cap_check_error"

    @staticmethod
    async def rollback_redis(
        offer_id: Optional[int],
        publisher_id: Optional[int],
        advertiser_id: Optional[int],
        db: AsyncSession,
        *,
        reservations: Optional[list[tuple]] = None,
    ) -> None:
        """仅按当前请求的 reservation token 回退 Redis；旧式无 token 调用安全拒绝。"""
        if not offer_id:
            return
        await rollback_cap_redis_counts(
            db=db,
            offer_id=offer_id,
            publisher_id=publisher_id,
            advertiser_id=advertiser_id,
            reservations=reservations,
        )
    
    @staticmethod
    async def increment_with_reservations(
        offer_id: Optional[int],
        publisher_id: Optional[int],
        advertiser_id: Optional[int],
        db: AsyncSession,
        reservation_context: Optional[dict] = None,
    ) -> Tuple[bool, str, list[tuple]]:
        """
        增加 Cap 并返回本次真正预留的 Redis 计数器列表。

        只回滚实际成功预留的 daily/total key，避免 fail-open 路径误减其它请求的计数。
        """
        if not offer_id:
            logger.debug("没有 Offer ID，跳过 Cap 计数递增")
            return True, "cap_ok", []

        result = await increment_cap_count(
            offer_id=offer_id,
            publisher_id=publisher_id,
            advertiser_id=advertiser_id,
            db=db,
            session_flush=True,
            include_reservations=True,
            reservation_context=reservation_context,
        )
        return result

    @staticmethod
    async def rollback_reservations(
        reservations: list[tuple],
    ) -> None:
        """按账本记录回滚 Redis；fail-open 记录只结束账本，不执行 DECR。"""
        failures = []
        for reservation in reservations:
            kind, offer_id, publisher_id = reservation[:3]
            reservation_date = reservation[3] if len(reservation) > 3 else None
            reservation_id = reservation[4] if len(reservation) > 4 else None
            ledger_key = reservation[5] if len(reservation) > 5 else None
            lease_owner = reservation[6] if len(reservation) > 6 else None
            redis_reserved = reservation[7] if len(reservation) > 7 else True
            try:
                if redis_reserved:
                    if kind == "daily":
                        result = await RedisCapManager.decrement_daily(
                            offer_id, publisher_id,
                            reservation_date=reservation_date,
                            reservation_id=reservation_id,
                        )
                    elif kind == "total":
                        result = await RedisCapManager.decrement_total(
                            offer_id, publisher_id, reservation_id=reservation_id
                        )
                    else:
                        failures.append(f"unknown kind={kind}, offer_id={offer_id}")
                        continue
                    if result < 0:
                        raise RuntimeError(
                            f"Redis rollback unresolved: kind={kind}, offer_id={offer_id}, token={reservation_id}"
                        )
                if ledger_key:
                    await CapReservationLedger.finalize(
                        ledger_key, "ROLLED_BACK", lease_owner=lease_owner
                    )
            except Exception as exc:
                if ledger_key:
                    try:
                        await CapReservationLedger.mark_needs_reconciliation(
                            ledger_key, str(exc), lease_owner=lease_owner
                        )
                    except Exception:
                        logger.critical(
                            "Cap Reservation 状态更新失败：%s", ledger_key, exc_info=True
                        )
                failures.append(
                    f"kind={kind}, offer_id={offer_id}, token={reservation_id}, error={exc}"
                )
                logger.error(
                    "Cap reservation rollback failed; continue with remaining tokens",
                    exc_info=True,
                )
        if failures:
            raise RuntimeError(
                "Cap reservation rollback incomplete: " + "; ".join(failures)
            )


    @staticmethod
    async def increment(
        offer_id: Optional[int],
        publisher_id: Optional[int],
        advertiser_id: Optional[int],
        db: AsyncSession,
    ) -> Tuple[bool, str]:
        """兼容旧调用签名；新事务代码应使用 increment_with_reservations。"""
        ok, status, _reservations = await CapChecker.increment_with_reservations(
            offer_id=offer_id,
            publisher_id=publisher_id,
            advertiser_id=advertiser_id,
            db=db,
        )
        return ok, status
