"""
Cap 限制检查器

检查转化是否超过 Cap 限制（Daily Cap / Total Cap）
"""
import logging
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cap import check_cap, increment_cap_count

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
            # Cap 检查失败不影响主流程，记录错误但继续
            return True, "cap_check_error"
    
    @staticmethod
    async def increment(
        offer_id: Optional[int],
        publisher_id: Optional[int],
        advertiser_id: Optional[int],
        db: AsyncSession,
        *,
        commit: bool = True,
    ) -> bool:
        """
        增加 Cap 计数

        Args:
            commit: 为 False 时仅 flush，由调用方统一 commit（与转化入库同事务）
        """
        if not offer_id:
            return False

        try:
            passed = await increment_cap_count(
                offer_id=offer_id,
                publisher_id=publisher_id,
                advertiser_id=advertiser_id,
                db=db,
            )
            if commit:
                await db.commit()
            else:
                await db.flush()
            if not passed:
                logger.warning(
                    "Cap 计数递增未通过：offer_id=%s publisher_id=%s",
                    offer_id,
                    publisher_id,
                )
                return False
            logger.debug(
                f"Cap 计数已增加：offer_id={offer_id}, publisher_id={publisher_id}"
            )
            return True
        except Exception as e:
            logger.error(f"增加 Cap 计数失败：{e}", exc_info=True)
            try:
                await db.rollback()
            except Exception as rollback_err:
                logger.warning("Cap 计数失败后回滚事务异常：%s", rollback_err)
            return False
