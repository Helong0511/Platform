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
    ) -> None:
        """DB 回滚后同步回退 Redis Cap 计数。"""
        if not offer_id:
            return
        await rollback_cap_redis_counts(
            db=db,
            offer_id=offer_id,
            publisher_id=publisher_id,
            advertiser_id=advertiser_id,
        )
    
    @staticmethod
    async def increment_with_reservations(
        offer_id: Optional[int],
        publisher_id: Optional[int],
        advertiser_id: Optional[int],
        db: AsyncSession,
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
        )
        return result

    @staticmethod
    async def rollback_reservations(
        reservations: list[tuple],
    ) -> None:
        """仅回滚当前请求确实预留成功的 Redis Cap key，不再重新查询 DB。"""
        for reservation in reservations:
            # 兼容历史三元组；新预留记录带业务日期，确保跨日回滚精确。
            kind, offer_id, publisher_id = reservation[:3]
            reservation_date = reservation[3] if len(reservation) > 3 else None
            reservation_id = reservation[4] if len(reservation) > 4 else None
            if kind == "daily":
                result = await RedisCapManager.decrement_daily(
                    offer_id,
                    publisher_id,
                    reservation_date=reservation_date,
                    reservation_id=reservation_id,
                )
            elif kind == "total":
                result = await RedisCapManager.decrement_total(
                    offer_id, publisher_id, reservation_id=reservation_id
                )
            else:
                logger.error("未知 Cap reservation 类型，跳过回滚：%s", kind)
                continue
            if result < 0:
                raise RuntimeError(
                    f"Cap reservation rollback failed: kind={kind}, offer_id={offer_id}, token={reservation_id}"
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
