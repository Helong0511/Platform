"""
Postback 处理流水线步骤（可单测）。

``PostbackProcessor`` 编排本模块函数，保持行为不变。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postback.checks.cap_checker import CapChecker
from app.core.postback.checks.discount_checker import DiscountChecker
from app.core.postback.savers.conversion_saver import ConversionSaver
from app.core.postback.transformers.click_associator import ClickAssociator
from app.core.postback.validators.duplicate_checker import DuplicateChecker
from app.models.models import PostbackConversion, ShortLink

logger = logging.getLogger(__name__)


@dataclass
class PostbackPipelineContext:
    """流水线上下文（步骤间传递）。"""

    platform: str
    raw_data: Dict[str, Any]
    db: AsyncSession
    request_ip: Optional[str] = None
    normalized_data: Dict[str, Any] = field(default_factory=dict)
    click_association: Optional[Dict[str, Any]] = None
    conversion_status: str = "Pending"
    final_payout: float = 0.0
    conversion: Optional[PostbackConversion] = None


async def step_associate_click(ctx: PostbackPipelineContext) -> Optional[Dict[str, Any]]:
    click_id = ctx.normalized_data.get("click_id")
    ctx.click_association = await ClickAssociator.associate(click_id, ctx.db)
    return ctx.click_association


async def step_check_duplicate(ctx: PostbackPipelineContext) -> bool:
    """返回 True 表示重复，应跳过后续入库。"""
    return await DuplicateChecker.is_duplicate(
        conversion_id=ctx.normalized_data.get("conversion_id"),
        click_id=ctx.normalized_data.get("click_id"),
        db=ctx.db,
    )


def attribution_ids_from_association(
    association: Optional[Dict[str, Any]],
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    if not association:
        return None, None, None
    return (
        association.get("offer_id"),
        association.get("publisher_id"),
        association.get("advertiser_id"),
    )


async def step_check_cap(ctx: PostbackPipelineContext) -> Tuple[bool, str]:
    offer_id, publisher_id, advertiser_id = attribution_ids_from_association(
        ctx.click_association
    )
    cap_ok, cap_status = await CapChecker.check(
        offer_id=offer_id,
        publisher_id=publisher_id,
        advertiser_id=advertiser_id,
        db=ctx.db,
    )
    ctx.conversion_status = "Pending" if cap_ok else f"CapExceeded({cap_status})"
    if not cap_ok and offer_id and publisher_id:
        try:
            stmt = (
                update(ShortLink)
                .where(
                    ShortLink.offer_id == offer_id,
                    ShortLink.channel_id == publisher_id,
                    ShortLink.is_active == True,
                )
                .values(is_active=False)
            )
            result = await ctx.db.execute(stmt)
            await ctx.db.commit()
            logger.info("Cap 超限已关闭短链 %s 条", result.rowcount)
        except Exception as e:
            logger.error("关闭短链失败: %s", e)
    return cap_ok, cap_status


async def step_apply_discount(ctx: PostbackPipelineContext) -> Tuple[float, Any]:
    offer_id, publisher_id, _ = attribution_ids_from_association(ctx.click_association)
    original = ctx.normalized_data.get("payout") or 0.0
    final_payout, info = await DiscountChecker.calculate(
        original_payout=original,
        offer_id=offer_id,
        publisher_id=publisher_id,
        product_id=ctx.normalized_data.get("product_id"),
        client_id=ctx.normalized_data.get("client_id"),
        db=ctx.db,
    )
    ctx.final_payout = final_payout
    return final_payout, info


async def step_save_conversion(ctx: PostbackPipelineContext) -> PostbackConversion:
    ctx.conversion = await ConversionSaver.save(
        normalized_data=ctx.normalized_data,
        click_association=ctx.click_association,
        final_payout=ctx.final_payout,
        conversion_status=ctx.conversion_status,
        db=ctx.db,
    )
    if ctx.click_association and ctx.conversion:
        await ConversionSaver.update_click_conversion(
            click_association=ctx.click_association,
            conversion_id=ctx.conversion.id,
            db=ctx.db,
        )
    return ctx.conversion
