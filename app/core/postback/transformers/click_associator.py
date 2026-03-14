"""
Click ID 关联器

通过 Click ID 关联 Click 记录，获取 Offer、Publisher 等信息
"""
import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.models.models import Click, Offer, Publisher, Advertiser

logger = logging.getLogger(__name__)


class ClickAssociator:
    """Click ID 关联器"""
    
    @staticmethod
    async def associate(
        click_id: Optional[str],
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        通过 Click ID 关联 Click 记录
        
        Args:
            click_id: Click ID
            db: 数据库会话
        
        Returns:
            dict: 关联信息（offer_id, publisher_id, advertiser_id, click_time 等）
            None: 如果未找到 Click 记录
        """
        if not click_id:
            logger.debug("Click ID 为空，无法关联")
            return None
        
        # 查询 Click 记录（带关联的 Offer、Publisher、Advertiser）
        result = await db.execute(
            select(Click)
            .options(
                joinedload(Click.offer),
                joinedload(Click.publisher),
                joinedload(Click.advertiser)
            )
            .where(Click.click_id == str(click_id))
            .limit(1)
        )
        
        click = result.scalars().first()
        
        if not click:
            logger.debug(f"未找到 Click 记录：click_id={click_id}")
            return None
        
        # 提取关联信息
        association = {
            'click_id': click.click_id,
            'offer_id': click.offer_id,
            'publisher_id': click.publisher_id,
            'advertiser_id': click.advertiser_id,
            'click_time': click.click_time,
            'ip': click.ip,
            'country': click.country,
            'device': click.device,
            'offer': click.offer,
            'publisher': click.publisher,
            'advertiser': click.advertiser,
        }
        
        logger.info(
            f"Click ID 关联成功：click_id={click_id}, "
            f"offer_id={click.offer_id}, publisher_id={click.publisher_id}"
        )
        
        return association
