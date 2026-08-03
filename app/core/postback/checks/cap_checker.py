"""
Cap 限制检查器

检查转化是否超过 Cap 限制（Daily Cap / Total Cap）
"""
import logging
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cap import check_cap, increment_cap_count, rollback_cap_redis_counts
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
    async def increment(
        offer_id: Optional[int],
        publisher_id: Optional[int],
        advertiser_id: Optional[int],
        db: AsyncSession,
    ) -> Tuple[bool, str]:
        """
        增加 Cap 计数（仅 flush，由 PostbackProcessor 统一 commit）。

        Returns:
            (ok, status)：status 为 cap_ok / cap_exceeded / cap_check_error
        """
        if not offer_id:
            logger.debug("没有 Offer ID，跳过 Cap 计数递增")
            return True, "cap_ok"

        redis_reserved = False
        try:
            passed, status = await increment_cap_count(
                offer_id=offer_id,
                publisher_id=publisher_id,
                advertiser_id=advertiser_id,
                db=db,
                session_flush=True,
            )
            if not passed:
                logger.warning(
                    "Cap 计数递增未通过：offer_id=%s publisher_id=%s status=%s",
                    offer_id,
                    publisher_id,
                    status,
                )
                return False, status or "cap_exceeded"
            # increment_cap_count 已成功预留 Redis；其后异常须由本层回退，避免与
            # increment 内部 except 的 reserved 回退叠加成双重 DECR。
            redis_reserved = True
            await db.flush()
            logger.debug(
                f"Cap 计数已增加：offer_id={offer_id}, publisher_id={publisher_id}"
            )
            return True, "cap_ok"
        except Exception as e:
            if redis_reserved:
                await rollback_cap_redis_counts(
                    db=db,
                    offer_id=offer_id,
                    publisher_id=publisher_id,
                    advertiser_id=advertiser_id,
                )
            logger.error(f"增加 Cap 计数失败：{e}", exc_info=True)
            raise
