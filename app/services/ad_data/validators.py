"""
广告数据入参校验模块。
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.country_code import find_country_code_by_any_format, preserve_unrecognized_country_code
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.utils import normalize_ad_unit
from app.models.models import Product

logger = logging.getLogger(__name__)

from app.core.ad_data_metadata import (
    normalize_data_source,
    normalize_report_type,
    normalize_upstream_account,
)

UPDATE_ALLOWED_FIELDS: Set[str] = {
    "product_id",
    "ad_unit",
    "country_code",
    "data_source",
    "upstream_account",
    "report_type",
    "request_count",
    "match_count",
    "display_count",
    "click_count",
    "viewability_rate",
    "ecpm_after_deduct",
    "ecpm_before_deduct",
    "revenue_after_deduct",
    "revenue_before_deduct",
}


class AdDataValidator:
    """广告数据验证器"""

    @staticmethod
    def filter_update_fields(update_data: Dict[str, Any]) -> Dict[str, Any]:
        """按白名单过滤可更新字段，并规范化 ad_unit。"""
        filtered = {k: v for k, v in update_data.items() if k in UPDATE_ALLOWED_FIELDS}
        if "ad_unit" in filtered:
            filtered["ad_unit"] = normalize_ad_unit(filtered["ad_unit"])
        if "data_source" in filtered:
            filtered["data_source"] = normalize_data_source(filtered["data_source"])
        if "report_type" in filtered:
            filtered["report_type"] = normalize_report_type(filtered["report_type"])
        if "upstream_account" in filtered:
            filtered["upstream_account"] = normalize_upstream_account(filtered["upstream_account"])
        return filtered

    @staticmethod
    async def validate_product_exists(db: AsyncSession, product_id: int) -> None:
        result = await db.execute(select(Product).where(Product.id == product_id))
        if not result.scalars().first():
            raise_api_exception(
                ErrorCode.AD_DATA_PRODUCT_NOT_FOUND,
                detail=f"指定的产品ID {product_id} 不存在，请确认产品是否存在",
            )

    @staticmethod
    async def resolve_country_code(db: AsyncSession, country_input: Optional[str]) -> Optional[str]:
        """解析并规范化国家代码；空值为 NULL；显式 ZZ 保留为全部区域。"""
        if not country_input or not str(country_input).strip():
            return None
        stripped = str(country_input).strip()
        if stripped == "ZZ":
            return "ZZ"
        found = await find_country_code_by_any_format(db, stripped)
        if found:
            return found
        return preserve_unrecognized_country_code(stripped)

    @staticmethod
    def needs_uniqueness_check(filtered_update_data: Dict[str, Any]) -> bool:
        identity_fields = {
            "product_id",
            "country_code",
            "ad_unit",
            "data_source",
            "report_type",
        }
        return bool(identity_fields.intersection(filtered_update_data))

    @staticmethod
    def validate_update_data(
            update_data: Dict[str, Any],
            is_admin: bool
    ) -> Tuple[bool, List[str]]:
        """
        验证更新数据
        
        Args:
            update_data: 更新数据字典
            is_admin: 是否管理员
        
        Returns:
            tuple: (是否通过验证，错误消息列表)
        """
        errors = []

        # 权限检查
        if not is_admin:
            errors.append("仅管理员可以更新广告数据")

        # 字段验证
        numeric_fields = [
            'request_count', 'match_count', 'display_count',
            'click_count', 'pageviews', 'ecpm_before_deduct',
            'ecpm_after_deduct', 'revenue_before_deduct',
            'revenue_after_deduct'
        ]

        for field in numeric_fields:
            if field in update_data:
                value = update_data[field]
                if value is not None:
                    try:
                        float(value)
                        if float(value) < 0:
                            errors.append(f"{field} 不能为负数")
                    except (ValueError, TypeError):
                        errors.append(f"{field} 必须是数字")

        # 日期格式验证
        if 'date' in update_data:
            try:
                if isinstance(update_data['date'], str):
                    datetime.fromisoformat(update_data['date'])
            except ValueError:
                errors.append(f"日期格式错误：{update_data['date']}")

        if errors:
            logger.warning(f"广告数据验证失败：errors={errors}")
            return False, errors

        return True, []
