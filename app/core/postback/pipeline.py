"""
Postback 处理流水线步骤（可单测）。

``PostbackProcessor`` 编排本模块函数，保持行为不变。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postback.checks.cap_checker import CapChecker
from app.core.postback.checks.discount_checker import DiscountChecker
from app.core.postback.savers.conversion_saver import ConversionSaver
from app.core.postback.transformers.click_associator import ClickAssociator
from app.core.postback.validators.duplicate_checker import DuplicateChecker
from app.models.models import Offer, PostbackConversion, ShortLink

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
    final_payout: Decimal = Decimal("0")
    trusted_client_id: Optional[int] = None
    trusted_product_id: Optional[int] = None
    trusted_attribution_resolved: bool = False
    conversion: Optional[PostbackConversion] = None
    cap_ok: bool = True
    skip_save_and_forward: bool = False


async def step_associate_click(ctx: PostbackPipelineContext) -> Optional[Dict[str, Any]]:
    """
    流水线步骤：根据 click_id 关联点击记录，填充归因上下文。

    Args:
        ctx: 流水线上下文（读写 normalized_data、click_association）

    Returns:
        Click 关联信息字典；无 click_id 或关联失败时可能为 None
    """
    click_id = ctx.normalized_data.get("click_id")
    ctx.click_association = await ClickAssociator.associate(click_id, ctx.db)
    return ctx.click_association


async def step_validate_offer_status(ctx: PostbackPipelineContext) -> bool:
    """
    流水线步骤：校验关联的 Offer 是否仍处于激活状态。

    Offer 下线（is_active=False 或 status != 'Active'）后，不再处理新转化，
    避免 Cap 占用、通知发送和数据污染。

    Args:
        ctx: 流水线上下文

    Returns:
        True 表示 Offer 有效，可继续处理；False 表示 Offer 已下线，应跳过。
    """
    offer_id, _, _ = attribution_ids_from_association(ctx.click_association)
    if not offer_id:
        return True  # 无 Offer ID（如直连 postback），不阻断

    # 优先使用关联结果中已加载的 ORM 对象
    offer_obj = None
    assoc = ctx.click_association or {}
    if isinstance(assoc.get("offer"), Offer):
        offer_obj = assoc["offer"]
    else:
        try:
            r = await ctx.db.execute(
                select(Offer).where(Offer.id == offer_id).limit(1)
            )
            offer_obj = r.scalars().first()
        except Exception as e:
            logger.warning("Offer 状态校验查询失败（放行）: offer_id=%s err=%s", offer_id, e)
            return True  # 查询失败不阻断，避免基础设施故障导致转化丢失

    if offer_obj and (not offer_obj.is_active or offer_obj.status != "Active"):
        logger.warning(
            "Offer 已下线，跳过转化处理: offer_id=%s is_active=%s status=%s",
            offer_id,
            offer_obj.is_active,
            offer_obj.status,
        )
        return False

    return True


async def step_check_duplicate(ctx: PostbackPipelineContext) -> bool:
    """返回 True 表示重复，应跳过后续入库。"""
    return await DuplicateChecker.is_duplicate(
        platform=ctx.platform,
        conversion_id=ctx.normalized_data.get("conversion_id"),
        event_name=ctx.normalized_data.get("event_name"),
        db=ctx.db,
    )


def conversion_status_for_cap(cap_ok: bool) -> str:
    """返回数据库可存储且稳定的转化状态；详细超限原因单独用于日志/响应。"""
    return "Pending" if cap_ok else "CapReached"


def attribution_ids_from_association(
    association: Optional[Dict[str, Any]],
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """
    从 Click 关联结果提取 offer / publisher / advertiser 三元组。

    Args:
        association: ``ClickAssociator.associate`` 返回的关联字典

    Returns:
        (offer_id, publisher_id, advertiser_id)，缺失字段为 None
    """
    if not association:
        return None, None, None
    return (
        association.get("offer_id"),
        association.get("publisher_id"),
        association.get("advertiser_id"),
    )


async def step_check_cap(ctx: PostbackPipelineContext) -> Tuple[bool, str]:
    """
    流水线步骤：检查 Cap 是否超限，超限时关闭对应短链并更新 conversion_status。

    Args:
        ctx: 流水线上下文

    Returns:
        (cap_ok, cap_status)：cap_ok 为 False 表示已超量
    """
    offer_id, publisher_id, advertiser_id = attribution_ids_from_association(
        ctx.click_association
    )
    cap_ok, cap_status = await CapChecker.check(
        offer_id=offer_id,
        publisher_id=publisher_id,
        advertiser_id=advertiser_id,
        db=ctx.db,
    )
    ctx.cap_ok = cap_ok
    ctx.conversion_status = conversion_status_for_cap(cap_ok)
    return cap_ok, cap_status


async def deactivate_short_links_on_cap_exceeded(
    db: AsyncSession,
    offer_id: int,
    publisher_id: int,
) -> int:
    """
    Cap 确认超限后关闭对应短链（与转化入库处于同一事务，由调用方 commit）。
    """
    stmt = (
        update(ShortLink)
        .where(
            ShortLink.offer_id == offer_id,
            ShortLink.channel_id == publisher_id,
            ShortLink.is_active == True,
        )
        .values(is_active=False)
    )
    result = await db.execute(stmt)
    count = result.rowcount or 0
    if count:
        logger.info("Cap 超限已关闭短链 %s 条", count)
    return count


async def step_apply_discount(ctx: PostbackPipelineContext) -> Tuple[Decimal, Any, bool]:
    """
    流水线步骤：按扣量规则计算最终 payout，写入 ctx.final_payout。

    Args:
        ctx: 流水线上下文

    Returns:
        (final_payout, discount_info, skip_save_and_forward)
    """
    offer_id, publisher_id, advertiser_id = attribution_ids_from_association(ctx.click_association)
    original = Decimal(str(ctx.normalized_data.get("payout") or 0))
    # 客户/产品归属从服务端点击与渠道关系解析，不能使用回调请求体覆盖。
    (
        ctx.trusted_client_id,
        ctx.trusted_product_id,
    ) = await ConversionSaver.resolve_trusted_attribution(
        normalized_data=ctx.normalized_data,
        click_association=ctx.click_association,
        db=ctx.db,
    )
    ctx.trusted_attribution_resolved = True

    final_payout, info, skip_save = await DiscountChecker.calculate(
        original_payout=original,
        offer_id=offer_id,
        publisher_id=publisher_id,
        product_id=ctx.trusted_product_id,
        client_id=ctx.trusted_client_id,
        advertiser_id=advertiser_id,
        click_id=ctx.normalized_data.get("click_id"),
        db=ctx.db,
    )
    ctx.final_payout = final_payout
    ctx.skip_save_and_forward = skip_save
    return final_payout, info, skip_save


async def step_save_conversion(ctx: PostbackPipelineContext) -> PostbackConversion:
    """
    流水线步骤：持久化转化记录，并回写 Click 表的 conversion_id。

    Args:
        ctx: 流水线上下文

    Returns:
        新建的 PostbackConversion 实例
    """
    ctx.conversion = await ConversionSaver.save(
        normalized_data=ctx.normalized_data,
        click_association=ctx.click_association,
        final_payout=ctx.final_payout,
        conversion_status=ctx.conversion_status,
        db=ctx.db,
        trusted_client_id=ctx.trusted_client_id,
        trusted_product_id=ctx.trusted_product_id,
        trusted_attribution_resolved=ctx.trusted_attribution_resolved,
    )
    if ctx.click_association and ctx.conversion:
        await ConversionSaver.update_click_conversion(
            click_association=ctx.click_association,
            conversion_id=ctx.conversion.id,
            db=ctx.db,
        )
    return ctx.conversion
