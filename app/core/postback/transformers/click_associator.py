"""
Click ID 关联器

通过 Click ID 关联 Click 或 ClickStats 记录，获取 Offer、Publisher 等信息
"""
import logging
import json
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.models.models import Click, ClickStats, Offer, Publisher, Advertiser

logger = logging.getLogger(__name__)


class ClickAssociator:
    """Click ID 关联器"""
    
    @staticmethod
    async def associate(
        click_id: Optional[str],
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        通过 Click ID 关联 Click 或 ClickStats 记录
        
        Args:
            click_id: Click ID
            db: 数据库会话
        
        Returns:
            dict: 关联信息（offer_id, publisher_id, advertiser_id, click_time 等）
            None: 如果未找到记录
        """
        if not click_id:
            logger.debug("Click ID 为空，无法关联")
            return None
        
        # 首先尝试查询 Click 记录（带关联的 Offer、Publisher、Advertiser）
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
        
        if click:
            # 解析 url_params
            url_params = {}
            if click.url_params:
                try:
                    url_params = json.loads(click.url_params)
                    logger.debug(f"成功解析 url_params: {url_params}")
                except json.JSONDecodeError:
                    logger.warning(f"解析 url_params 失败: {click.url_params}")
            
            # 提取关联信息
            association = {
                'click_id': click.click_id,
                'offer_id': click.offer_id,
                'publisher_id': click.publisher_id,
                'advertiser_id': click.advertiser_id,
                'short_link_id': click.short_link_id,
                'click_time': click.click_time,
                'ip': click.ip,
                'country': click.country,
                'device': click.device,
                'os': click.os,
                'offer': click.offer,
                'publisher': click.publisher,
                'advertiser': click.advertiser,
                'url_params': url_params,
            }
            
            logger.info(
                f"从 Click 表关联成功：click_id={click_id}, "
                f"offer_id={click.offer_id}, publisher_id={click.publisher_id}"
            )
            
            return association
        
        logger.debug(f"未在 Click 表找到记录，尝试 ClickStats 表：click_id={click_id}")
        
        # 如果 Click 表没有，尝试查询 ClickStats 表
        result_stats = await db.execute(
            select(ClickStats)
            .where(ClickStats.click_id == str(click_id))
            .limit(1)
        )
        
        click_stats = result_stats.scalars().first()
        
        if click_stats:
            # 从 ClickStats 表提取关联信息
            offer = None
            publisher = None
            advertiser = None
            
            # 手动查询关联对象
            if click_stats.offer_id:
                offer_result = await db.execute(
                    select(Offer).where(Offer.id == click_stats.offer_id)
                )
                offer = offer_result.scalars().first()
            
            if click_stats.publisher_id:
                publisher_result = await db.execute(
                    select(Publisher).where(Publisher.id == click_stats.publisher_id)
                )
                publisher = publisher_result.scalars().first()
            
            if click_stats.advertiser_id:
                advertiser_result = await db.execute(
                    select(Advertiser).where(Advertiser.id == click_stats.advertiser_id)
                )
                advertiser = advertiser_result.scalars().first()
            
            association = {
                'click_id': click_stats.click_id,
                'offer_id': click_stats.offer_id,
                'publisher_id': click_stats.publisher_id,
                'advertiser_id': click_stats.advertiser_id,
                'short_link_id': None,  # ClickStats 表没有这个字段
                'click_time': click_stats.click_time,
                'ip': None,  # ClickStats 表没有这个字段
                'country': None,  # ClickStats 表没有这个字段
                'device': None,  # ClickStats 表没有这个字段
                'os': None,  # ClickStats 表没有这个字段
                'offer': offer,
                'publisher': publisher,
                'advertiser': advertiser,
                'url_params': {},  # ClickStats 表没有这个字段
            }
            
            logger.info(
                f"从 ClickStats 表关联成功：click_id={click_id}, "
                f"offer_id={click_stats.offer_id}, publisher_id={click_stats.publisher_id}"
            )
            
            return association
        
        logger.debug(f"在 Click 和 ClickStats 表都未找到记录：click_id={click_id}")
        return None
