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
from app.services.cpl.deduction.helpers import DeductionScopeLockError

logger = logging.getLogger(__name__)


class DiscountChecker:
    """扣量计算器"""

    @staticmethod
    def _resolve_config_scope(config: Any) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """只使用最终命中配置自身的唯一层级 ID 作为扣量统计范围。

        请求归因中的另外两个 ID 仅用于配置查找和审计日志，不能把同一配置
        的 24 小时统计拆成多个子范围。数据库旧表没有三选一 CHECK 约束，
        因此遇到零个或多个 scope 时必须 fail-closed，避免静默选错财务口径。
        """
        scope = (
            getattr(config, "advertiser_id", None),
            getattr(config, "offer_id", None),
            getattr(config, "publisher_id", None),
        )
        populated = [value for value in scope if value is not None]
        if len(populated) != 1 or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in populated
        ):
            raise DeductionProcessingError(
                "扣量配置层级数据异常：advertiser_id、offer_id、publisher_id 必须且只能设置一个正整数"
            )
        return scope

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
        event_identity: Optional[Dict[str, str]] = None,
        currency: str = "USD",
        currency_source: str = "system_fallback_usd",
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
                # 统计范围由最终命中的配置层级决定，不使用请求归因的完整 ID 组合。
                scope_advertiser_id, scope_offer_id, scope_publisher_id = (
                    DiscountChecker._resolve_config_scope(config)
                )
                conversion_data = {
                    "original_payout": final_payout,
                    "currency": currency,
                    "currency_source": currency_source,
                }
                result = await apply_deduction(
                    db=db,
                    conversion_data=conversion_data,
                    config=config,
                    click_id=click_id,
                    advertiser_id=scope_advertiser_id,
                    offer_id=scope_offer_id,
                    publisher_id=scope_publisher_id,
                    event_identity=event_identity,
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
                        # DB 扣量审计日志是财务凭证；Redis fail-open 不能吞掉持久化失败。
                        logger.error("记录扣量日志失败，回滚本次 Postback：%s", log_exc)
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
                            # DB 扣金额日志是财务凭证；持久化失败必须回滚并重试。
                            logger.error("记录扣金额日志失败，回滚本次 Postback：%s", log_exc)
                            raise DeductionProcessingError(
                                f"记录扣金额日志失败: {log_exc}"
                            ) from log_exc
        except DeductionScopeLockError as exc:
            # scope 锁不可用时绝不能按 DEDUCTION_FAIL_OPEN 当作“无配置”继续处理。
            raise DeductionProcessingError(
                "扣量 scope 锁获取失败，拒绝在无锁状态下执行财务决策"
            ) from exc
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
