"""
转化扣减（CPL）配置管理服务层。

薄编排层：CRUD 命令 + queries/helpers/mappers 委托。
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Request
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.core.audit_log import log_delete
from app.core.errors import ErrorCode
from app.core.exceptions import is_http_exception, raise_api_exception
from app.models.models import ConversionDeductionConfig, ConversionDeductionLog, User
from app.schemas.cpl.deduction import (
    ConversionDeductionConfigResponse,
    ConversionDeductionLogResponse,
    DeductionStatsResponse,
)
from app.services.base_service import BaseService
from app.services.cpl.deduction import helpers as deduction_helpers
from app.services.cpl.deduction import mappers as deduction_mappers
from app.services.cpl.deduction.helpers import ConfigLevel, resolve_config_level_target
from app.services.cpl.deduction.queries.config_list_query import DeductionConfigListQuery
from app.services.cpl.deduction.queries.logs_query import DeductionLogsQuery
from app.services.cpl.deduction.queries.stats_query import DeductionStatsQuery

logger = logging.getLogger(__name__)


class ConversionDeductionService(BaseService[ConversionDeductionConfig]):
    """CPL 转化扣减配置服务。"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, ConversionDeductionConfig)

    async def create_deduction_config(
        self,
        config_data: Dict[str, Any],
        current_user: User,
    ) -> ConversionDeductionConfig:
        if not config_data.get("enable_volume_deduction") and not config_data.get(
            "enable_amount_deduction"
        ):
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="请至少启用一种扣减方式（扣量或扣金额）",
            )

        level: ConfigLevel = config_data.get("level")
        target_id = config_data.get("target_id")
        if not level or not target_id:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="配置层级和目标ID不能为空",
            )

        await deduction_helpers.validate_target_exists(self.db, level, target_id)
        await deduction_helpers.check_existing_config(self.db, level, target_id)
        fields = deduction_helpers.build_config_fields(level, target_id, config_data)
        config = ConversionDeductionConfig(**fields)

        try:
            self.db.add(config)
            await self.db.flush()
            await self.db.refresh(config)
            await deduction_helpers.invalidate_config_cache(level, target_id)
            config = await deduction_helpers.load_config_with_relations(self.db, config.id)
            logger.info(
                "扣减配置创建成功: config_id=%s, level=%s, target_id=%s",
                config.id,
                level,
                target_id,
            )
            return config
        except Exception as e:
            await self.db.rollback()
            logger.error(
                "创建扣减配置失败: level=%s, target_id=%s, error=%s",
                level,
                target_id,
                str(e),
                exc_info=True,
            )
            if is_http_exception(e):
                raise
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"创建扣减配置失败: {str(e)}",
            )

    async def get_deduction_configs(
        self,
        page: int = 1,
        page_size: int = 20,
        level: Optional[str] = None,
        is_active: Optional[bool] = None,
        keyword: Optional[str] = None,
        advertiser_id: Optional[int] = None,
    ) -> Tuple[List[ConversionDeductionConfig], int]:
        return await DeductionConfigListQuery(self.db).fetch(
            page=page,
            page_size=page_size,
            level=level,
            is_active=is_active,
            keyword=keyword,
            advertiser_id=advertiser_id,
        )

    async def get_deduction_config_by_id(
        self, config_id: int
    ) -> Optional[ConversionDeductionConfig]:
        query = (
            select(ConversionDeductionConfig)
            .where(ConversionDeductionConfig.id == config_id)
            .options(
                joinedload(ConversionDeductionConfig.advertiser),
                joinedload(ConversionDeductionConfig.offer),
                joinedload(ConversionDeductionConfig.publisher),
            )
        )
        result = await self.db.execute(query)
        return result.unique().scalars().first()

    async def update_deduction_config(
        self,
        config_id: int,
        update_data: Dict[str, Any],
        current_user: User,
    ) -> ConversionDeductionConfig:
        config = await self.get_deduction_config_by_id(config_id)
        if not config:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"扣减配置ID {config_id} 不存在",
            )

        level, target_id = resolve_config_level_target(config)
        for field, value in update_data.items():
            if field in ("level", "target_id"):
                continue
            if hasattr(config, field):
                setattr(config, field, value)

        try:
            await self.db.flush()
            await self.db.refresh(config)
            if level and target_id:
                await deduction_helpers.invalidate_config_cache(level, target_id)
            config = await deduction_helpers.load_config_with_relations(self.db, config_id)
            logger.info("扣减配置更新成功: config_id=%s", config_id)
            return config
        except Exception as e:
            await self.db.rollback()
            logger.error(
                "更新扣减配置失败: config_id=%s, error=%s",
                config_id,
                str(e),
                exc_info=True,
            )
            if is_http_exception(e):
                raise
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新扣减配置失败: {str(e)}",
            )

    async def update_deduction_config_status(
        self,
        config_id: int,
        is_active: bool,
        current_user: User,
    ) -> ConversionDeductionConfig:
        config = await self.get_deduction_config_by_id(config_id)
        if not config:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"扣减配置ID {config_id} 不存在",
            )

        level, target_id = resolve_config_level_target(config)
        config.is_active = is_active

        try:
            await self.db.flush()
            await self.db.refresh(config)
            if level and target_id:
                await deduction_helpers.invalidate_config_cache(level, target_id)
            logger.info(
                "扣减配置状态更新成功: config_id=%s, is_active=%s",
                config_id,
                is_active,
            )
            return config
        except Exception as e:
            await self.db.rollback()
            logger.error(
                "更新扣减配置状态失败: config_id=%s, error=%s",
                config_id,
                str(e),
                exc_info=True,
            )
            if is_http_exception(e):
                raise
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新扣减配置状态失败: {str(e)}",
            )

    async def delete_deduction_config(
        self,
        config_id: int,
        current_user: User,
        request: Optional[Request] = None,
    ) -> None:
        config = await self.get_deduction_config_by_id(config_id)
        if not config:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"扣减配置ID {config_id} 不存在",
            )

        level, target_id = resolve_config_level_target(config)

        try:
            await log_delete(
                db=self.db,
                user=current_user,
                resource_type="CONVERSION_DEDUCTION_CONFIG",
                resource_id=config.id,
                resource_name=f"扣减配置-{config.id}",
                request=request,
            )
            await self.db.delete(config)
            await self.db.flush()
            if level and target_id:
                await deduction_helpers.invalidate_config_cache(level, target_id)
            logger.info("扣减配置删除成功: config_id=%s", config_id)
        except Exception as e:
            await self.db.rollback()
            logger.error(
                "删除扣减配置失败: config_id=%s, error=%s",
                config_id,
                str(e),
                exc_info=True,
            )
            if is_http_exception(e):
                raise
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"删除扣减配置失败: {str(e)}",
            )

    async def batch_update_status(
        self,
        config_ids: List[int],
        is_active: bool,
        current_user: User,
    ) -> int:
        if not config_ids:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="配置ID列表不能为空",
            )

        result = await self.db.execute(
            select(ConversionDeductionConfig).where(
                ConversionDeductionConfig.id.in_(config_ids)
            )
        )
        configs = result.scalars().all()
        if len(configs) != len(config_ids):
            found_ids = {config.id for config in configs}
            missing_ids = set(config_ids) - found_ids
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"以下配置ID不存在: {', '.join(map(str, missing_ids))}",
            )

        try:
            await self.db.execute(
                update(ConversionDeductionConfig)
                .where(ConversionDeductionConfig.id.in_(config_ids))
                .values(is_active=is_active)
            )
            await self.db.flush()

            for config in configs:
                level, target_id = resolve_config_level_target(config)
                if level and target_id:
                    await deduction_helpers.invalidate_config_cache(level, target_id)

            logger.info(
                "批量更新扣减配置状态成功: config_ids=%s, is_active=%s, count=%s",
                config_ids,
                is_active,
                len(configs),
            )
            return len(configs)
        except Exception as e:
            await self.db.rollback()
            logger.error(
                "批量更新扣减配置状态失败: config_ids=%s, error=%s",
                config_ids,
                str(e),
                exc_info=True,
            )
            if is_http_exception(e):
                raise
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"批量更新扣减配置状态失败: {str(e)}",
            )

    async def batch_delete(
        self,
        config_ids: List[int],
        current_user: User,
        request: Optional[Request] = None,
    ) -> int:
        if not config_ids:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="配置ID列表不能为空",
            )

        result = await self.db.execute(
            select(ConversionDeductionConfig).where(
                ConversionDeductionConfig.id.in_(config_ids)
            )
        )
        configs = result.scalars().all()
        if len(configs) != len(config_ids):
            found_ids = {config.id for config in configs}
            missing_ids = set(config_ids) - found_ids
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"以下配置ID不存在: {', '.join(map(str, missing_ids))}",
            )

        for config in configs:
            await log_delete(
                db=self.db,
                user=current_user,
                resource_type="CONVERSION_DEDUCTION_CONFIG",
                resource_id=config.id,
                resource_name=f"扣减配置-{config.id}",
                request=request,
            )

        try:
            await self.db.execute(
                delete(ConversionDeductionConfig).where(
                    ConversionDeductionConfig.id.in_(config_ids)
                )
            )
            await self.db.flush()

            for config in configs:
                level, target_id = resolve_config_level_target(config)
                if level and target_id:
                    await deduction_helpers.invalidate_config_cache(level, target_id)

            logger.info(
                "批量删除扣减配置成功: config_ids=%s, count=%s",
                config_ids,
                len(configs),
            )
            return len(configs)
        except Exception as e:
            await self.db.rollback()
            logger.error(
                "批量删除扣减配置失败: config_ids=%s, error=%s",
                config_ids,
                str(e),
                exc_info=True,
            )
            if is_http_exception(e):
                raise
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"批量删除扣减配置失败: {str(e)}",
            )

    async def get_deduction_stats(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        group_by: Optional[str] = None,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        return await DeductionStatsQuery(self.db).fetch(
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
        )

    async def get_deduction_logs(
        self,
        page: int = 1,
        page_size: int = 20,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        conversion_id: Optional[int] = None,
        click_id: Optional[str] = None,
    ) -> Tuple[List[ConversionDeductionLog], int]:
        return await DeductionLogsQuery(self.db).fetch(
            page=page,
            page_size=page_size,
            start_date=start_date,
            end_date=end_date,
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
            conversion_id=conversion_id,
            click_id=click_id,
        )

    @staticmethod
    def to_config_response(
        config: ConversionDeductionConfig,
    ) -> ConversionDeductionConfigResponse:
        return deduction_mappers.to_config_response(config)

    def to_config_response_list(
        self, configs: List[ConversionDeductionConfig]
    ) -> List[ConversionDeductionConfigResponse]:
        return deduction_mappers.to_config_response_list(configs)

    @staticmethod
    def to_log_response(log: ConversionDeductionLog) -> ConversionDeductionLogResponse:
        return deduction_mappers.to_log_response(log)

    def to_log_response_list(
        self, logs: List[ConversionDeductionLog]
    ) -> List[ConversionDeductionLogResponse]:
        return deduction_mappers.to_log_response_list(logs)

    @staticmethod
    def config_to_export_row(config: ConversionDeductionConfig) -> Dict[str, Any]:
        return deduction_mappers.config_to_export_row(config)

    def log_to_export_row(self, log: ConversionDeductionLog) -> Dict[str, Any]:
        return deduction_mappers.log_to_export_row(log)

    @staticmethod
    def stats_to_export_rows(stats: DeductionStatsResponse) -> List[Dict[str, Any]]:
        return deduction_mappers.stats_to_export_rows(stats)
