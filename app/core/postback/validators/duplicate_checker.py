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
        conversion_id: str,
        click_id: Optional[str],
        db: AsyncSession
    ) -> bool:
        """
        检查转化是否已处理过
        
        Args:
            conversion_id: 转化 ID
            click_id: 点击 ID
            db: 数据库会话
        
        Returns:
            bool: 是否重复
        """
        # 检查conversion_id是否已存在
        if conversion_id:
            result = await db.execute(
                select(PostbackConversion.id)
                .where(PostbackConversion.conversion_id == conversion_id)
                .limit(1)
            )
            existing = result.scalar_one_or_none()
            if existing:
                logger.info(f"检测到重复转化：conversion_id={conversion_id}")
                return True
        
        # 检查click_id是否已存在
        if click_id:
            result = await db.execute(
                select(PostbackConversion.id)
                .where(PostbackConversion.click_id == click_id)
                .limit(1)
            )
            existing = result.scalar_one_or_none()
            if existing:
                logger.info(f"检测到重复转化：click_id={click_id}")
                return True
        
        logger.debug(f"转化未重复：conversion_id={conversion_id}, click_id={click_id}")
        return False
