"""转化扣减（Conversion Deduction）配置管理 API

职责：按广告主/Offer/渠道层级配置转化扣减规则，并提供统计、日志查询与 Excel 导出。

权限：
- 全部端点：仅管理员（转化扣减规则属商业机密，禁止客户拉取）

主要端点（前缀 /conversion-deductions）：
- POST   /                      创建扣减配置
- GET    /                      分页列表
- PUT    /{config_id}           更新
- DELETE /{config_id}           删除
- PATCH  /{config_id}/status    启用/停用
- POST   /batch/update-status   批量改状态
- POST   /batch/delete          批量删除
- GET    /stats                 扣减统计
- GET    /logs                  扣减执行日志
- GET    /export                导出 Excel。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
import logging
from typing import Optional

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
from app.core.excel_io import excel_streaming_response
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
    """
    创建转化扣减配置。

    权限：仅管理员。
    支持广告主/Offer/渠道三个层级，配置扣减比例与策略。
    """
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
    dependencies=[Depends(require_admin)],
)
async def get_deduction_configs(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
        level: Optional[str] = Query(None),
        is_active: Optional[bool] = Query(None),
        keyword: Optional[str] = Query(None),
        advertiser_id: Optional[int] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
):
    """
    分页查询转化扣减配置列表。

    权限：仅管理员（扣减规则属商业机密，禁止客户拉取）。
    """
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
    """
    更新转化扣减配置。

    权限：仅管理员；支持部分字段更新。
    """
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
    """
    删除指定 ID 的转化扣减配置（物理删除）。

    删除后不再对新转化生效；历史扣减日志保留。
    权限：仅管理员。
    """
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
    """
    切换单条扣减配置的启用状态（is_active 查询参数）。

    禁用后该配置不再参与新转化的扣减计算。
    权限：仅管理员。
    """
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
    """
    批量切换多条扣减配置的启用状态。

    请求体含 config_ids 列表与目标 is_active；返回成功/失败计数。
    权限：仅管理员。
    """
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
    """
    按 ID 列表批量删除扣减配置。

    适用于清理过期或错误配置；历史日志不受影响。
    权限：仅管理员。
    """
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
    """
    查询扣减统计数据。

    权限：登录用户；可按时间、层级、目标 ID 聚合。
    """
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
    """
    分页查询扣减执行日志。

    权限：登录用户；记录每次扣减决策与结果。
    """
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
    """
    按筛选条件导出扣减配置列表为 Excel 文件流。

    支持 level、is_active、keyword、advertiser_id 过滤。
    权限：仅管理员；响应用于浏览器下载。
    """
    # ---------- 入口：参数与依赖准备 ----------
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    # ---------- 异常处理 ----------
    try:
        configs, _ = await svc.get_deduction_configs(
            page=1,
            page_size=10000,
            level=level,
            is_active=is_active,
            keyword=keyword,
            advertiser_id=advertiser_id,
        )
        # ---------- 条件分支 ----------
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
        return excel_streaming_response(rows, "扣减配置", "扣减配置")
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
    """
    导出扣减统计数据为 Excel 文件。

    权限：仅管理员。
    """
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
        return excel_streaming_response(rows, "扣减统计", "扣减统计")
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
    """
    导出扣减执行日志为 Excel 文件。

    权限：仅管理员。
    """
    # ---------- 入口：参数与依赖准备 ----------
    svc: ConversionDeductionService = await get_conversion_deduction_service(db)
    # ---------- 异常处理 ----------
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
        # ---------- 条件分支 ----------
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
        return excel_streaming_response(rows, "扣减日志", "扣减日志")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("导出扣减日志失败: %s", e, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=str(e))
