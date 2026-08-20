"""
扣量计算器

根据 OfferDiscount（比例扣价）与 ConversionDeductionConfig（扣量/扣金额）计算最终 payout。
"""
import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deduction import apply_deduction, find_deduction_config, log_deduction
from app.core.discount import calculate_discount
from app.core.postback.errors import DeductionProcessingError

logger = logging.getLogger(__name__)


class DiscountChecker:
    """扣量计算器"""

    @staticmethod
    async def calculate(
        original_payout: Decimal | float | int | str,
        offer_id: Optional[int],
        publisher_id: Optional[int],
        product_id: Optional[int],
        client_id: Optional[int],
        advertiser_id: Optional[int],
        click_id: Optional[str],
        db: AsyncSession,
    ) -> Tuple[Decimal, Dict[str, Any], bool]:
        """
        计算扣量后的金额。

        Returns:
            (最终金额, 扣量详情, 是否跳过入库与下游转发)
        """
        deduction_info: Dict[str, Any] = {
            "original_payout": original_payout,
            "offer_discount": None,
            "deduction_config": None,
            "final_payout": original_payout,
        }
        final_payout = Decimal(str(original_payout or 0))
        skip_save_and_forward = False

        # 1. OfferDiscount 比例扣价（offer / channel / publisher 默认）
        if offer_id and publisher_id:
            try:
                discounted_payout, discount_amount, discount_desc = await calculate_discount(
                    db=db,
                    offer_id=offer_id,
                    publisher_id=publisher_id,
                    original_payout=final_payout,
                )
                if discount_desc:
                    deduction_info["offer_discount"] = {
                        "description": discount_desc,
                        "deducted": discount_amount,
                        "final_payout": discounted_payout,
                    }
                    final_payout = discounted_payout
                    logger.debug(
                        "OfferDiscount 扣价：offer_id=%s publisher_id=%s final=%s",
                        offer_id,
                        publisher_id,
                        final_payout,
                    )
            except Exception as exc:
                logger.warning("OfferDiscount 计算失败：%s", exc)
                if not settings.DEDUCTION_FAIL_OPEN:
                    raise DeductionProcessingError(
                        f"OfferDiscount 计算失败: {exc}"
                    ) from exc

        # 2. ConversionDeductionConfig（扣量 / 扣金额）
        try:
            config = await find_deduction_config(
                db=db,
                advertiser_id=advertiser_id,
                offer_id=offer_id,
                publisher_id=publisher_id,
            )
            if config:
                conversion_data = {"original_payout": final_payout}
                result = await apply_deduction(
                    db=db,
                    conversion_data=conversion_data,
                    config=config,
                    click_id=click_id,
                    advertiser_id=advertiser_id,
                    offer_id=offer_id,
                    publisher_id=publisher_id,
                )
                deduction_info["deduction_config"] = result

                if result.get("should_deduct_volume"):
                    skip_save_and_forward = True
                    final_payout = Decimal("0")
                    try:
                        await log_deduction(
                            db=db,
                            deduction_result=result,
                            click_id=click_id,
                            advertiser_id=advertiser_id,
                            offer_id=offer_id,
                            publisher_id=publisher_id,
                            config=config,
                            deduction_reason="postback_volume_deduction",
                        )
                    except Exception as log_exc:
                        logger.warning("记录扣量日志失败：%s", log_exc)
                        if not settings.DEDUCTION_FAIL_OPEN:
                            raise DeductionProcessingError(
                                f"记录扣量日志失败: {log_exc}"
                            ) from log_exc
                    logger.info(
                        "转化扣量命中：offer_id=%s publisher_id=%s，跳过入库与转发",
                        offer_id,
                        publisher_id,
                    )
                else:
                    final_payout = Decimal(str(result.get("final_amount", final_payout)))
                    if result.get("should_deduct_amount"):
                        try:
                            await log_deduction(
                                db=db,
                                deduction_result=result,
                                click_id=click_id,
                                advertiser_id=advertiser_id,
                                offer_id=offer_id,
                                publisher_id=publisher_id,
                                config=config,
                                deduction_reason="postback_amount_deduction",
                            )
                        except Exception as log_exc:
                            logger.warning("记录扣金额日志失败：%s", log_exc)
                            if not settings.DEDUCTION_FAIL_OPEN:
                                raise DeductionProcessingError(
                                    f"记录扣金额日志失败: {log_exc}"
                                ) from log_exc
        except DeductionProcessingError:
            raise
        except Exception as exc:
            logger.warning("ConversionDeductionConfig 处理失败：%s", exc)
            if not settings.DEDUCTION_FAIL_OPEN:
                raise DeductionProcessingError(
                    f"ConversionDeductionConfig 处理失败: {exc}"
                ) from exc

        deduction_info["final_payout"] = final_payout
        return final_payout, deduction_info, skip_save_and_forward
