"""
Click ID 关联器

通过 Click ID 关联 Click 记录，获取 Offer、Publisher 等信息
"""
import asyncio
import logging
import json
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.core.tracking.click_token import resolve_click_from_token
from app.models.models import Click, Offer, Publisher, Advertiser

logger = logging.getLogger(__name__)


class ClickAssociator:
    """Click ID 关联器"""

    @staticmethod
    async def associate(
        click_id: Optional[str],
        db: AsyncSession,
    ) -> Optional[Dict[str, Any]]:
        """
        关联 Click：优先解析追踪令牌（新格式），失败则查 clicks 表（旧格式/落库延迟）。
        """
        if not click_id:
            logger.debug("Click ID 为空，无法关联")
            return None

        token_assoc = resolve_click_from_token(click_id)
        if token_assoc:
            return await ClickAssociator._enrich_association(token_assoc, db)

        return await ClickAssociator.associate_from_db(click_id, db)

    @staticmethod
    async def _enrich_association(
        association: Dict[str, Any],
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        令牌解析仅有 ID 时，按需加载 Offer/Publisher/Advertiser ORM（供通知等逻辑使用）。
        转发等流程仅需 publisher_id，不依赖本步骤。
        """
        if not association.get("_from_token"):
            return association

        offer_id = association.get("offer_id")
        publisher_id = association.get("publisher_id")
        advertiser_id = association.get("advertiser_id")

        try:
            if publisher_id and association.get("publisher") is None:
                r = await db.execute(
                    select(Publisher).where(Publisher.id == publisher_id).limit(1)
                )
                association["publisher"] = r.scalars().first()
            if offer_id and association.get("offer") is None:
                r = await db.execute(
                    select(Offer).where(Offer.id == offer_id).limit(1)
                )
                association["offer"] = r.scalars().first()
            if advertiser_id and association.get("advertiser") is None:
                r = await db.execute(
                    select(Advertiser).where(Advertiser.id == advertiser_id).limit(1)
                )
                association["advertiser"] = r.scalars().first()
        except Exception as e:
            logger.warning("令牌关联 ORM  enrichment 失败（不影响 ID 归因）: %s", e)

        return association

    @staticmethod
    async def associate_from_db(
        click_id: Optional[str],
        db: AsyncSession,
    ) -> Optional[Dict[str, Any]]:
        """
        通过 clicks 表关联（兼容旧版随机 click_id 及异步落库延迟）。
        """
        if not click_id:
            logger.debug("Click ID 为空，无法关联")
            return None

        logger.info(f"开始关联 Click ID（数据库）: {click_id}")
        
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
                        # 指数退避：delay = base_delay * (2 ^ attempt)
                        delay = base_delay * (2 ** attempt)
                        logger.debug(f"等待 {delay:.2f} 秒后重试...")
                        await asyncio.sleep(delay)
            except Exception as e:
                logger.error(f"第 {attempt + 1} 次尝试查询 Click 记录失败：{e}")
                if attempt < max_attempts - 1:
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
