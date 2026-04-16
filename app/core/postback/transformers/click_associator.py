"""
Click ID 关联器

通过 Click ID 关联 Click 记录，获取 Offer、Publisher 等信息
"""
import logging
import json
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
        
        logger.info(f"开始关联 Click ID: {click_id}")
        
        # 使用指数退避策略重试查询，处理批量处理延迟问题
        max_attempts = 5
        base_delay = 0.3  # 基础延迟 300ms
        
        for attempt in range(max_attempts):
            # 查询 Click 记录（带关联的 Offer、Publisher、Advertiser）
            try:
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
                    logger.info(f"第 {attempt + 1} 次尝试：找到 Click 记录：id={click.id}, click_id={click.click_id}")
                    break
                else:
                    logger.warning(f"第 {attempt + 1} 次尝试：未找到 Click 记录：click_id={click_id}")
                    if attempt < max_attempts - 1:
                        import asyncio
                        # 指数退避：delay = base_delay * (2 ^ attempt)
                        delay = base_delay * (2 ** attempt)
                        logger.debug(f"等待 {delay:.2f} 秒后重试...")
                        await asyncio.sleep(delay)
            except Exception as e:
                logger.error(f"第 {attempt + 1} 次尝试查询 Click 记录失败：{e}")
                if attempt < max_attempts - 1:
                    import asyncio
                    # 指数退避：delay = base_delay * (2 ^ attempt)
                    delay = base_delay * (2 ** attempt)
                    logger.debug(f"等待 {delay:.2f} 秒后重试...")
                    await asyncio.sleep(delay)
        
        if not click:
            logger.error(f"多次尝试后仍未找到 Click 记录：click_id={click_id}")
            return None
        
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
            'user_agent': click.user_agent,
            'country': click.country,
            'device': click.device,
            'os': click.os,
            'offer': click.offer,
            'publisher': click.publisher,
            'advertiser': click.advertiser,
            'url_params': url_params,
        }
        
        logger.info(
            f"Click ID 关联成功：click_id={click_id}, "
            f"offer_id={click.offer_id}, publisher_id={click.publisher_id}"
        )
        
        return association
