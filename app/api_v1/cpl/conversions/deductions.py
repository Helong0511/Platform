"""
转化扣减配置管理 API（薄路由层）
"""
import logging
from io import BytesIO
from typing import Optional
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, Depends, Query, Path, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_PAGE_SIZE
from app.core.database import get_db
from app.core.dependencies import get_conversion_deduction_service
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import get_current_user, require_admin
from app.core.audit_log import (
    log_user_action,
    log_activate,
    log_deactivate,
    commit_audit_log,
)
from app.core.utils import get_app_now_naive
from app.models.models import User
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.cpl.deduction import (
    ConversionDeductionConfigCreate,
    ConversionDeductionConfigUpdate,
    ConversionDeductionConfigResponse,
    ConversionDeductionLogResponse,
    DeductionStatsResponse,
    BatchUpdateStatusRequest,
    BatchDeleteRequest,
)
from app.services.cpl.conversion_deduction_service import ConversionDeductionService

router = APIRouter()
logger = logging.getLogger(__name__)


def _excel_response(rows: list, sheet_name: str, filename_prefix: str) -> StreamingResponse:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df = pd.DataFrame(rows)
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        worksheet = writer.sheets[sheet_name]
        for column_cells in worksheet.columns:
            max_length = max(
                len(str(cell.value)) for cell in column_cells
            ) if column_cells else 0
            worksheet.column_dimensions[column_cells[0].column_letter].width = min(
                max_length + 2, 50
            )
    output.seek(0)
    filename = f"{filename_prefix}_{get_app_now_naive().strftime('%Y%m%d_%H%M%S')}.xlsx"
    encoded_filename = quote(filename.encode("utf-8"))
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.post(
    "/",
    response_model=ResponseBaseSchema[ConversionDeductionConfigResponse],
    summary="创建扣减配置",
    dependencies=[Depends(require_admin)],
)
async def create_deduction_config(
        request: Request,
        config_in: ConversionDeductionConfigCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    config = await svc.create_deduction_config(config_in.model_dump(), current_user)
    await log_user_action(
        db=db,
        action_type="CREATE",
        user=current_user,
        resource_type="CONVERSION_DEDUCTION_CONFIG",
        resource_id=config.id,
        resource_name=f"扣减配置-{config.id}",
        request=request,
        success=True,
    )
    await commit_audit_log(db)
    return ResponseBaseSchema.success(data=svc.to_config_response(config))


@router.get(
    "/",
    response_model=PaginatedResponseBaseSchema[list[ConversionDeductionConfigResponse]],
    summary="获取扣减配置列表",
)
async def get_deduction_configs(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
        level: Optional[str] = Query(None),
        is_active: Optional[bool] = Query(None),
        keyword: Optional[str] = Query(None),
        advertiser_id: Optional[int] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    try:
        configs, total = await svc.get_deduction_configs(
            page=page,
            page_size=page_size,
            level=level,
            is_active=is_active,
            keyword=keyword,
            advertiser_id=advertiser_id,
        )
        return PaginatedResponseBaseSchema.success(
            data=svc.to_config_response_list(configs),
            total=total,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取扣减配置列表失败: %s", e, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=str(e))


@router.put(
    "/{config_id}",
    response_model=ResponseBaseSchema[ConversionDeductionConfigResponse],
    summary="更新扣减配置",
    dependencies=[Depends(require_admin)],
)
async def update_deduction_config(
        request: Request,
        config_id: int = Path(..., ge=1),
        config_in: ConversionDeductionConfigUpdate = ...,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    update_data = config_in.model_dump(exclude_unset=True)
    config = await svc.update_deduction_config(config_id, update_data, current_user)
    await log_user_action(
        db=db,
        action_type="UPDATE",
        user=current_user,
        resource_type="CONVERSION_DEDUCTION_CONFIG",
        resource_id=config.id,
        resource_name=f"扣减配置-{config.id}",
        request=request,
        success=True,
        details=update_data,
    )
    await commit_audit_log(db)
    return ResponseBaseSchema.success(data=svc.to_config_response(config))


@router.delete(
    "/{config_id}",
    response_model=ResponseBaseSchema[dict],
    summary="删除扣减配置",
    dependencies=[Depends(require_admin)],
)
async def delete_deduction_config(
        request: Request,
        config_id: int = Path(..., ge=1),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    await svc.delete_deduction_config(config_id, current_user, request=request)
    return ResponseBaseSchema.success(data={"id": config_id})


@router.patch(
    "/{config_id}/status",
    response_model=ResponseBaseSchema[dict],
    summary="更新扣减配置状态",
    dependencies=[Depends(require_admin)],
)
async def update_deduction_config_status(
        request: Request,
        config_id: int = Path(..., ge=1),
        is_active: bool = Query(...),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    before = await svc.get_deduction_config_by_id(config_id)
    if not before:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"扣减配置ID {config_id} 不存在",
        )
    old_is_active = before.is_active
    await svc.update_deduction_config_status(config_id, is_active, current_user)
    if old_is_active != is_active:
        if is_active:
            await log_activate(
                db=db,
                user=current_user,
                resource_type="CONVERSION_DEDUCTION_CONFIG",
                resource_id=config_id,
                resource_name=f"扣减配置-{config_id}",
                request=request,
            )
        else:
            await log_deactivate(
                db=db,
                user=current_user,
                resource_type="CONVERSION_DEDUCTION_CONFIG",
                resource_id=config_id,
                resource_name=f"扣减配置-{config_id}",
                request=request,
            )
        await commit_audit_log(db)
    return ResponseBaseSchema.success(data={"id": config_id, "is_active": is_active})


@router.post(
    "/batch/update-status",
    response_model=ResponseBaseSchema[dict],
    summary="批量更新扣减配置状态",
    dependencies=[Depends(require_admin)],
)
async def batch_update_deduction_config_status(
        request: Request,
        request_data: BatchUpdateStatusRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    updated_count = await svc.batch_update_status(
        request_data.config_ids, request_data.is_active, current_user
    )
    if updated_count > 0:
        action = "ACTIVATE" if request_data.is_active else "DEACTIVATE"
        await log_user_action(
            db=db,
            action_type=action,
            user=current_user,
            resource_type="CONVERSION_DEDUCTION_CONFIG",
            resource_id=0,
            resource_name="批量更新扣减配置状态",
            request=request,
            details={
                "config_ids": request_data.config_ids,
                "is_active": request_data.is_active,
                "updated_count": updated_count,
            },
        )
        await commit_audit_log(db)
    return ResponseBaseSchema.success(
        data={"updated_count": updated_count, "is_active": request_data.is_active}
    )


@router.post(
    "/batch/delete",
    response_model=ResponseBaseSchema[dict],
    summary="批量删除扣减配置",
    dependencies=[Depends(require_admin)],
)
async def batch_delete_deduction_configs(
        request: Request,
        request_data: BatchDeleteRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    deleted_count = await svc.batch_delete(request_data.config_ids, current_user, request=request)
    return ResponseBaseSchema.success(data={"deleted_count": deleted_count})


@router.get(
    "/stats",
    response_model=ResponseBaseSchema[DeductionStatsResponse],
    summary="获取扣减统计",
    dependencies=[Depends(require_admin)],
)
async def get_deduction_stats(
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
        group_by: Optional[str] = Query("time"),
        advertiser_id: Optional[int] = Query(None),
        offer_id: Optional[int] = Query(None),
        publisher_id: Optional[int] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    try:
        stats_data = await svc.get_deduction_stats(
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
        )
        return ResponseBaseSchema.success(data=DeductionStatsResponse(**stats_data))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取扣减统计失败: %s", e, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=str(e))


@router.get(
    "/logs",
    response_model=PaginatedResponseBaseSchema[list[ConversionDeductionLogResponse]],
    summary="获取扣减日志",
    dependencies=[Depends(require_admin)],
)
async def get_deduction_logs(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
        advertiser_id: Optional[int] = Query(None),
        offer_id: Optional[int] = Query(None),
        publisher_id: Optional[int] = Query(None),
        conversion_id: Optional[int] = Query(None),
        click_id: Optional[str] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    try:
        logs, total = await svc.get_deduction_logs(
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
        return PaginatedResponseBaseSchema.success(
            data=svc.to_log_response_list(logs),
            total=total,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取扣减日志失败: %s", e, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=str(e))


@router.get(
    "/export",
    response_class=StreamingResponse,
    summary="导出扣减配置",
    dependencies=[Depends(require_admin)],
)
async def export_deduction_configs(
        request: Request,
        level: Optional[str] = Query(None),
        is_active: Optional[bool] = Query(None),
        keyword: Optional[str] = Query(None),
        advertiser_id: Optional[int] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    try:
        configs, _ = await svc.get_deduction_configs(
            page=1,
            page_size=10000,
            level=level,
            is_active=is_active,
            keyword=keyword,
            advertiser_id=advertiser_id,
        )
        if not configs:
            raise_api_exception(
                ErrorCode.NOT_FOUND,
                message="无数据，不能导出",
                detail="当前筛选条件下没有可导出的配置数据",
            )
        rows = [svc.config_to_export_row(c) for c in configs]
        logger.info("扣减配置导出: user=%s count=%s", current_user.username, len(rows))
        await log_user_action(
            db=db,
            action_type="EXPORT",
            user=current_user,
            resource_type="CONVERSION_DEDUCTION_CONFIG",
            request=request,
            details={"row_count": len(rows), "export_type": "configs"},
        )
        await commit_audit_log(db)
        return _excel_response(rows, "扣减配置", "扣减配置")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("导出扣减配置失败: %s", e, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=str(e))


@router.get(
    "/stats/export",
    response_class=StreamingResponse,
    summary="导出扣减统计",
    dependencies=[Depends(require_admin)],
)
async def export_deduction_stats(
        request: Request,
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
        group_by: Optional[str] = Query("time"),
        advertiser_id: Optional[int] = Query(None),
        offer_id: Optional[int] = Query(None),
        publisher_id: Optional[int] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    try:
        stats_data = await svc.get_deduction_stats(
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
        )
        stats = DeductionStatsResponse(**stats_data)
        rows = svc.stats_to_export_rows(stats)
        await log_user_action(
            db=db,
            action_type="EXPORT",
            user=current_user,
            resource_type="CONVERSION_DEDUCTION_CONFIG",
            request=request,
            details={"row_count": len(rows), "export_type": "stats"},
        )
        await commit_audit_log(db)
        return _excel_response(rows, "扣减统计", "扣减统计")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("导出扣减统计失败: %s", e, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=str(e))


@router.get(
    "/logs/export",
    response_class=StreamingResponse,
    summary="导出扣减日志",
    dependencies=[Depends(require_admin)],
)
async def export_deduction_logs(
        request: Request,
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
        advertiser_id: Optional[int] = Query(None),
        offer_id: Optional[int] = Query(None),
        publisher_id: Optional[int] = Query(None),
        conversion_id: Optional[int] = Query(None),
        click_id: Optional[str] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    try:
        logs, _ = await svc.get_deduction_logs(
            page=1,
            page_size=10000,
            start_date=start_date,
            end_date=end_date,
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
            conversion_id=conversion_id,
            click_id=click_id,
        )
        if not logs:
            raise_api_exception(
                ErrorCode.NOT_FOUND,
                message="无数据，不能导出",
                detail="当前筛选条件下没有可导出的日志数据",
            )
        rows = [svc.log_to_export_row(log) for log in logs]
        await log_user_action(
            db=db,
            action_type="EXPORT",
            user=current_user,
            resource_type="CONVERSION_DEDUCTION_CONFIG",
            request=request,
            details={"row_count": len(rows), "export_type": "logs"},
        )
        await commit_audit_log(db)
        return _excel_response(rows, "扣减日志", "扣减日志")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("导出扣减日志失败: %s", e, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=str(e))
