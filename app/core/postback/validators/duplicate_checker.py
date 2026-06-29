"""
重复检测器

防止重复处理相同的转化事件（与 DB 唯一约束 platform+conversion_id+event_name 对齐）
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
        conversion_id: Optional[str],
        event_name: Optional[str],
        db: AsyncSession,
    ) -> bool:
        """
        检查转化是否已处理过。

        Args:
            platform: 平台名称
            conversion_id: 转化 ID
            event_name: 事件名称
            db: 数据库会话

        Returns:
            bool: 是否重复
        """
        if not conversion_id:
            logger.debug("conversion_id 为空，跳过重复检测")
            return False

        normalized_event = event_name or ""

        result = await db.execute(
            select(PostbackConversion.id)
            .where(
                PostbackConversion.platform == platform,
                PostbackConversion.conversion_id == conversion_id,
                PostbackConversion.event_name == normalized_event,
            )
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info(
                "检测到重复转化：platform=%s conversion_id=%s event_name=%s",
                platform,
                conversion_id,
                normalized_event,
            )
            return True

        logger.debug(
            "转化未重复：platform=%s conversion_id=%s event_name=%s",
            platform,
            conversion_id,
            normalized_event,
        )
        return False
