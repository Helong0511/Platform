"""
重复检测器

防止重复处理相同的转化事件
"""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import PostbackConversion

logger = logging.getLogger(__name__)


class DuplicateChecker:
    """重复检测器"""
    
    @staticmethod
    async def is_duplicate(
        platform: str,
        conversion_id: str,
        event_name: str,
        db: AsyncSession
    ) -> bool:
        """
        检查转化是否已处理过
        
        Args:
            platform: 平台名称
            conversion_id: 转化 ID
            event_name: 事件名称
            db: 数据库会话
        
        Returns:
            bool: 是否重复
        """
        # 基于 platform + conversion_id + event_name 的唯一性检查
        result = await db.execute(
            select(PostbackConversion.id)
            .where(
                PostbackConversion.platform == platform,
                PostbackConversion.conversion_id == conversion_id,
                PostbackConversion.event_name == event_name
            )
            .limit(1)
        )
        
        existing = result.scalar_one_or_none()
        
        if existing:
            logger.info(
                f"检测到重复转化：platform={platform}, "
                f"conversion_id={conversion_id}, event_name={event_name}"
            )
            return True
        
        logger.debug(
            f"转化未重复：platform={platform}, "
            f"conversion_id={conversion_id}, event_name={event_name}"
        )
        return False
