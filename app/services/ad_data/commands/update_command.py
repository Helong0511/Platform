"""
广告数据更新命令。

功能说明：
- 校验、唯一性预检、字段写入与持久化
- 统一处理 IntegrityError 友好提示

在系统中的位置：
- 被 ``AdDataService.update_ad_data`` 调用
"""
import logging
import re
from typing import Any, Dict

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import handle_integrity_error, raise_api_exception
from app.core.security import is_admin
from app.models.models import AdData, User
from app.services.ad_data.queries.uniqueness_query import AdDataUniquenessQuery
from app.services.ad_data.validators import AdDataValidator, UPDATE_ALLOWED_FIELDS

logger = logging.getLogger(__name__)

_RATE_FIELDS = frozenset({"request_count", "match_count", "display_count", "click_count"})


class AdDataUpdateCommand:
    """广告数据更新流程编排。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(
        self,
        data_id: int,
        update_data: Dict[str, Any],
        current_user: User,
    ) -> AdData:
        if not is_admin(current_user):
            raise_api_exception(
                ErrorCode.AD_DATA_UPDATE_FORBIDDEN,
                detail="仅管理员可以更新广告数据。客户用户没有更新权限",
            )

        ad_data = await self._load_or_raise(data_id)
        filtered = await self._prepare_update(ad_data, update_data)
        self._apply_fields(ad_data, filtered)
        await self._persist(ad_data, filtered, data_id)
        return ad_data

    async def _load_or_raise(self, data_id: int) -> AdData:
        result = await self.db.execute(select(AdData).where(AdData.id == data_id))
        ad_data = result.scalars().first()
        if not ad_data:
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"广告数据ID {data_id} 不存在",
            )
        return ad_data

    async def _prepare_update(
        self,
        ad_data: AdData,
        update_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        filtered = AdDataValidator.filter_update_fields(update_data)

        if "product_id" in filtered:
            await AdDataValidator.validate_product_exists(self.db, filtered["product_id"])

        if "country_code" in filtered:
            filtered["country_code"] = await AdDataValidator.resolve_country_code(
                self.db, filtered["country_code"]
            )

        if AdDataValidator.needs_uniqueness_check(filtered):
            new_product_id = filtered.get("product_id", ad_data.product_id)
            new_country_code = filtered.get("country_code", ad_data.country_code)
            new_ad_unit = filtered.get("ad_unit", ad_data.ad_unit or "")
            new_data_source = filtered.get("data_source", ad_data.data_source or "legacy")
            new_report_type = filtered.get("report_type", ad_data.report_type or "legacy")
            new_upstream_account = filtered.get("upstream_account", ad_data.upstream_account or "")

            uniqueness = AdDataUniquenessQuery(self.db)
            conflict = await uniqueness.find_conflict(
                ad_data,
                new_product_id,
                new_country_code,
                new_ad_unit,
                data_source=new_data_source,
                report_type=new_report_type,
                upstream_account=new_upstream_account,
            )
            if conflict:
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=await uniqueness.build_conflict_message(
                        conflict, ad_data, new_product_id, new_country_code
                    ),
                )
        return filtered

    def _apply_fields(self, ad_data: AdData, filtered: Dict[str, Any]) -> None:
        for key, value in filtered.items():
            if key in UPDATE_ALLOWED_FIELDS and hasattr(ad_data, key):
                setattr(ad_data, key, value)
        if _RATE_FIELDS.intersection(filtered):
            ad_data.finalize_metrics()

    async def _persist(
        self,
        ad_data: AdData,
        filtered: Dict[str, Any],
        data_id: int,
    ) -> None:
        try:
            self.db.add(ad_data)
            await self.db.flush()
            await self.db.refresh(ad_data)
        except Exception as e:
            if isinstance(e, IntegrityError):
                await self._handle_integrity_error(e, ad_data, filtered)
            error_msg = str(e)
            logger.error("更新广告数据失败: %s", error_msg, exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新广告数据失败：{error_msg}。请检查数据格式或联系管理员",
            )
        logger.info("广告数据已更新: ID=%s", data_id)

    async def _handle_integrity_error(
        self,
        error: IntegrityError,
        ad_data: AdData,
        filtered: Dict[str, Any],
    ) -> None:
        error_msg = str(error)
        conflict_info = ""
        match = re.search(r"Duplicate entry '([^']+)'", error_msg)
        if match:
            conflict_info = f"冲突的键值: {match.group(1)}"

        new_product_id = filtered.get("product_id", ad_data.product_id)
        new_country_code = filtered.get("country_code", ad_data.country_code)
        new_ad_unit = filtered.get("ad_unit", ad_data.ad_unit or "")

        custom_message = await AdDataUniquenessQuery(self.db).build_integrity_conflict_message(
            ad_data,
            new_product_id,
            new_country_code,
            new_ad_unit,
            conflict_info,
        )
        handle_integrity_error(
            error=error,
            constraint_name="uq_ad_data_identity",
            custom_message=custom_message,
            log_context="Update ad data",
        )
