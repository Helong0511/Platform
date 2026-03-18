"""
转化扣减配置管理 API

重构说明:
- 简化响应构建逻辑
- 提取公共响应构建方法
- 改进错误处理
"""
import logging
from io import BytesIO
from typing import Optional
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, Depends, Query, Path
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_PAGE_SIZE
from app.core.database import get_db
from app.core.dependencies import get_conversion_deduction_service
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import get_current_user, require_admin
from app.core.utils import get_app_now_naive
from app.models.models import (
    User,
    ConversionDeductionConfig,
    ConversionDeductionLog,
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.cpl.deduction import (
    ConversionDeductionConfigCreate,
    ConversionDeductionConfigUpdate,
    ConversionDeductionConfigResponse,
    ConversionDeductionLogResponse,
    DeductionStatsResponse,
    BatchUpdateStatusRequest,
    BatchDeleteRequest
)
from app.services.cpl.conversion_deduction_service import ConversionDeductionService

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_config_response(config: ConversionDeductionConfig) -> ConversionDeductionConfigResponse:
    """
    构建配置响应对象
    
    Args:
        config: 配置对象
        
    Returns:
        配置响应对象
    """
    config_data = ConversionDeductionConfigResponse.model_validate(config)

    # 设置层级和目标信息
    if config.advertiser:
        config_data.target_name = config.advertiser.advertiser_name
        config_data.advertiser_name = config.advertiser.advertiser_name
        config_data.level = 'advertiser'
        config_data.target_id = config.advertiser_id
    elif config.offer:
        config_data.target_name = config.offer.offer_name
        config_data.offer_name = config.offer.offer_name
        config_data.level = 'offer'
        config_data.target_id = config.offer_id
    elif config.publisher:
        config_data.target_name = config.publisher.publisher_name
        config_data.publisher_name = config.publisher.publisher_name
        config_data.level = 'publisher'
        config_data.target_id = config.publisher_id

    return config_data


def _build_log_response(log: ConversionDeductionLog) -> ConversionDeductionLogResponse:
    """
    构建日志响应对象
    
    Args:
        log: 日志对象
        
    Returns:
        日志响应对象
    """
    log_data = ConversionDeductionLogResponse.model_validate(log)

    # 设置关联信息
    if log.advertiser:
        log_data.advertiser_name = log.advertiser.advertiser_name
    if log.offer:
        log_data.offer_name = log.offer.offer_name
    if log.publisher:
        log_data.publisher_name = log.publisher.publisher_name

    return log_data


@router.post("/",
             response_model=ResponseBaseSchema[ConversionDeductionConfigResponse],
             summary="创建扣减配置",
             dependencies=[Depends(require_admin)])
async def create_deduction_config(
        config_in: ConversionDeductionConfigCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """创建扣减配置（仅管理员）"""
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)

    # 准备扣减配置数据
    config_data = config_in.model_dump()

    # 调用服务层创建扣减配置
    config = await deduction_service.create_deduction_config(config_data, current_user)

    # 构建响应数据
    config_response = _build_config_response(config)

    return ResponseBaseSchema.success(data=config_response)


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[ConversionDeductionConfigResponse]],
            summary="获取扣减配置列表")
async def get_deduction_configs(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        level: Optional[str] = Query(None, description="配置层级过滤"),
        is_active: Optional[bool] = Query(None, description="状态过滤"),
        keyword: Optional[str] = Query(None, description="搜索关键词（配置对象名称）"),
        advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """获取扣减配置列表"""
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)

    try:
        # 调用服务层获取扣减配置列表
        configs, total = await deduction_service.get_deduction_configs(
            page=page,
            page_size=page_size,
            level=level,
            is_active=is_active,
            keyword=keyword,
            advertiser_id=advertiser_id
        )

        # 转换为响应格式
        config_list = [_build_config_response(config) for config in configs]

        return PaginatedResponseBaseSchema.success(
            data=config_list,
            total=total,
            page=page,
            page_size=page_size
        )
    except Exception as e:
        logger.error(f"获取扣减配置列表失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取扣减配置列表失败: {str(e)}"
        )


@router.put("/{config_id}",
            response_model=ResponseBaseSchema[ConversionDeductionConfigResponse],
            summary="更新扣减配置",
            dependencies=[Depends(require_admin)])
async def update_deduction_config(
        config_id: int = Path(..., ge=1, description="配置ID"),
        config_in: ConversionDeductionConfigUpdate = ...,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """更新扣减配置（仅管理员）"""
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)

    # 准备更新数据
    update_data = config_in.model_dump(exclude_unset=True)

    # 调用服务层更新扣减配置
    config = await deduction_service.update_deduction_config(config_id, update_data, current_user)

    # 构建响应数据
    config_response = _build_config_response(config)

    return ResponseBaseSchema.success(data=config_response)


@router.delete("/{config_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除扣减配置",
               dependencies=[Depends(require_admin)])
async def delete_deduction_config(
        config_id: int = Path(..., ge=1, description="配置ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """删除扣减配置（仅管理员）"""
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)

    # 调用服务层删除扣减配置
    await deduction_service.delete_deduction_config(config_id, current_user)

    return ResponseBaseSchema.success(data={"id": config_id})


@router.patch("/{config_id}/status",
              response_model=ResponseBaseSchema[dict],
              summary="更新扣减配置状态",
              dependencies=[Depends(require_admin)])
async def update_deduction_config_status(
        config_id: int = Path(..., ge=1, description="配置ID"),
        is_active: bool = Query(..., description="是否激活"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """更新扣减配置状态（仅管理员）"""
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)

    # 调用服务层更新扣减配置状态
    await deduction_service.update_deduction_config_status(config_id, is_active, current_user)

    return ResponseBaseSchema.success(data={"id": config_id, "is_active": is_active})


@router.post("/batch/update-status",
             response_model=ResponseBaseSchema[dict],
             summary="批量更新扣减配置状态",
             dependencies=[Depends(require_admin)])
async def batch_update_deduction_config_status(
        request_data: BatchUpdateStatusRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """批量更新扣减配置状态（仅管理员）"""
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)

    # 调用服务层批量更新扣减配置状态
    updated_count = await deduction_service.batch_update_status(
        request_data.config_ids,
        request_data.is_active,
        current_user
    )

    return ResponseBaseSchema.success(data={
        "updated_count": updated_count,
        "is_active": request_data.is_active
    })


@router.post("/batch/delete",
             response_model=ResponseBaseSchema[dict],
             summary="批量删除扣减配置",
             dependencies=[Depends(require_admin)])
async def batch_delete_deduction_configs(
        request_data: BatchDeleteRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """批量删除扣减配置（仅管理员）"""
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)

    # 调用服务层批量删除扣减配置
    deleted_count = await deduction_service.batch_delete(
        request_data.config_ids,
        current_user
    )

    return ResponseBaseSchema.success(data={
        "deleted_count": deleted_count
    })


@router.get("/stats",
            response_model=ResponseBaseSchema[DeductionStatsResponse],
            summary="获取扣减统计",
            dependencies=[Depends(require_admin)])
async def get_deduction_stats(
        start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        group_by: Optional[str] = Query("time", description="分组方式：time/advertiser/offer/publisher"),
        advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
        offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
        publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """获取扣减统计（仅管理员）"""
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)

    try:
        # 调用服务层获取扣减统计
        stats_data = await deduction_service.get_deduction_stats(
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id
        )

        stats = DeductionStatsResponse(**stats_data)
        return ResponseBaseSchema.success(data=stats)
    except Exception as e:
        logger.error(f"获取扣减统计失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取扣减统计失败: {str(e)}"
        )


@router.get("/logs",
            response_model=PaginatedResponseBaseSchema[list[ConversionDeductionLogResponse]],
            summary="获取扣减日志",
            dependencies=[Depends(require_admin)])
async def get_deduction_logs(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
        offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
        publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
        conversion_id: Optional[int] = Query(None, description="转化ID过滤"),
        click_id: Optional[str] = Query(None, description="点击ID过滤"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """获取扣减日志（仅管理员）"""
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)

    try:
        # 调用服务层获取扣减日志
        logs, total = await deduction_service.get_deduction_logs(
            page=page,
            page_size=page_size,
            start_date=start_date,
            end_date=end_date,
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
            conversion_id=conversion_id,
            click_id=click_id
        )

        # 转换为响应格式
        log_list = [_build_log_response(log) for log in logs]

        return PaginatedResponseBaseSchema.success(
            data=log_list,
            total=total,
            page=page,
            page_size=page_size
        )
    except Exception as e:
        logger.error(f"获取扣减日志失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取扣减日志失败: {str(e)}"
        )


@router.get("/export",
            response_class=StreamingResponse,
            summary="导出扣减配置",
            dependencies=[Depends(require_admin)])
async def export_deduction_configs(
        level: Optional[str] = Query(None, description="配置层级过滤"),
        is_active: Optional[bool] = Query(None, description="状态过滤"),
        keyword: Optional[str] = Query(None, description="搜索关键词"),
        advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """导出扣减配置到Excel文件（仅管理员）"""
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)

    try:
        # 获取所有配置数据（不分页）
        configs, total = await deduction_service.get_deduction_configs(
            page=1,
            page_size=10000,  # 使用大值获取所有数据
            level=level,
            is_active=is_active,
            keyword=keyword,
            advertiser_id=advertiser_id
        )

        # 如果没有数据，抛出错误提示用户
        if not configs:
            raise_api_exception(
                ErrorCode.NOT_FOUND,
                message="无数据，不能导出",
                detail="当前筛选条件下没有可导出的配置数据，请调整筛选条件后重试"
            )

        # 准备导出数据
        data = []
        for config in configs:
            # 确定配置层级和目标名称
            level_name = ""
            target_name = ""
            if config.advertiser:
                level_name = "广告主"
                target_name = config.advertiser.advertiser_name
            elif config.offer:
                level_name = "Offer"
                target_name = config.offer.offer_name
            elif config.publisher:
                level_name = "渠道"
                target_name = config.publisher.publisher_name

            # 确定扣减策略名称
            strategy_name = {
                'random': '随机',
                'proportional': '按比例',
                'round_robin': '轮询'
            }.get(config.deduction_strategy, config.deduction_strategy)

            row = {
                "配置ID": config.id,
                "配置层级": level_name,
                "配置对象": target_name,
                "启用扣量": "是" if config.enable_volume_deduction else "否",
                "扣量比例": f"{(config.volume_deduction_ratio * 100):.2f}%" if config.enable_volume_deduction else "0%",
                "扣减策略": strategy_name if config.enable_volume_deduction else "-",
                "启用扣金额": "是" if config.enable_amount_deduction else "否",
                "扣金额比例": f"{(config.amount_deduction_ratio * 100):.2f}%" if config.enable_amount_deduction else "0%",
                "优先级": config.priority,
                "状态": "启用" if config.is_active else "禁用",
                "创建时间": config.created_at.strftime("%Y-%m-%d %H:%M:%S") if config.created_at else "",
                "更新时间": config.updated_at.strftime("%Y-%m-%d %H:%M:%S") if config.updated_at else "",
            }
            data.append(row)

        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df = pd.DataFrame(data)
            df.to_excel(writer, index=False, sheet_name="扣减配置")

            # 设置列宽自适应
            worksheet = writer.sheets["扣减配置"]
            for column_cells in worksheet.columns:
                max_length = max(len(str(cell.value)) for cell in column_cells) if column_cells else 0
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 2, 50)

        output.seek(0)
        filename = f"扣减配置_{get_app_now_naive().strftime('%Y%m%d_%H%M%S')}.xlsx"
        encoded_filename = quote(filename.encode('utf-8'))

        logger.info(f"扣减配置导出成功: 用户={current_user.username}, 数量={len(data)}")

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    except Exception as e:
        logger.error(f"导出扣减配置失败: {str(e)}", exc_info=True)
        if isinstance(e, type(raise_api_exception)):
            raise
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"导出扣减配置失败: {str(e)}"
        )


@router.get("/stats/export",
            response_class=StreamingResponse,
            summary="导出扣减统计",
            dependencies=[Depends(require_admin)])
async def export_deduction_stats(
        start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        group_by: Optional[str] = Query("time", description="分组方式：time/advertiser/offer/publisher"),
        advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
        offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
        publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """导出扣减统计到Excel文件（仅管理员）"""
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)

    try:
        # 获取统计数据
        stats_data = await deduction_service.get_deduction_stats(
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id
        )

        stats = DeductionStatsResponse(**stats_data)

        # 准备导出数据
        data = []

        # 汇总数据
        summary_row = {
            "类型": "汇总",
            "原始转化数量": stats.original_volume,
            "扣减转化数量": stats.deducted_volume,
            "最终转化数量": stats.final_volume,
            "扣量比例": f"{(stats.volume_deduction_ratio * 100):.2f}%",
            "原始转化金额": f"${stats.original_amount:.2f}",
            "扣减转化金额": f"${stats.deducted_amount:.2f}",
            "最终转化金额": f"${stats.final_amount:.2f}",
            "扣金额比例": f"{(stats.amount_deduction_ratio * 100):.2f}%",
        }
        data.append(summary_row)

        # 详细数据（如果有分组）
        if stats.items:
            for item in stats.items:
                row = {
                    "类型": item.get('name', '未知'),
                    "原始转化数量": item.get('original_volume', 0),
                    "扣减转化数量": item.get('deducted_volume', 0),
                    "最终转化数量": item.get('final_volume', 0),
                    "扣量比例": f"{(item.get('volume_deduction_ratio', 0) * 100):.2f}%",
                    "原始转化金额": f"${item.get('original_amount', 0):.2f}",
                    "扣减转化金额": f"${item.get('deducted_amount', 0):.2f}",
                    "最终转化金额": f"${item.get('final_amount', 0):.2f}",
                    "扣金额比例": f"{(item.get('amount_deduction_ratio', 0) * 100):.2f}%",
                }
                data.append(row)

        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df = pd.DataFrame(data)
            df.to_excel(writer, index=False, sheet_name="扣减统计")

            # 设置列宽自适应
            worksheet = writer.sheets["扣减统计"]
            for column_cells in worksheet.columns:
                max_length = max(len(str(cell.value)) for cell in column_cells) if column_cells else 0
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 2, 50)

        output.seek(0)
        filename = f"扣减统计_{get_app_now_naive().strftime('%Y%m%d_%H%M%S')}.xlsx"
        encoded_filename = quote(filename.encode('utf-8'))

        logger.info(f"扣减统计导出成功: 用户={current_user.username}")

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    except Exception as e:
        logger.error(f"导出扣减统计失败: {str(e)}", exc_info=True)
        if isinstance(e, type(raise_api_exception)):
            raise
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"导出扣减统计失败: {str(e)}"
        )


@router.get("/logs/export",
            response_class=StreamingResponse,
            summary="导出扣减日志",
            dependencies=[Depends(require_admin)])
async def export_deduction_logs(
        start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
        offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
        publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
        conversion_id: Optional[int] = Query(None, description="转化ID过滤"),
        click_id: Optional[str] = Query(None, description="点击ID过滤"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """导出扣减日志到Excel文件（仅管理员）"""
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)

    try:
        # 获取所有日志数据（不分页，使用大值）
        logs, total = await deduction_service.get_deduction_logs(
            page=1,
            page_size=10000,  # 使用大值获取所有数据
            start_date=start_date,
            end_date=end_date,
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
            conversion_id=conversion_id,
            click_id=click_id
        )

        # 如果没有数据，抛出错误提示用户
        if not logs:
            raise_api_exception(
                ErrorCode.NOT_FOUND,
                message="无数据，不能导出",
                detail="当前筛选条件下没有可导出的日志数据，请调整筛选条件后重试"
            )

        # 准备导出数据
        data = []
        # 策略标签映射
        strategy_map = {
            'random': '随机',
            'proportional': '按比例',
            'round_robin': '轮询'
        }

        for log in logs:
            # 构建日志响应对象以获取格式化数据
            log_response = _build_log_response(log)

            # 获取策略标签
            strategy_label = strategy_map.get(log_response.deduction_strategy, log_response.deduction_strategy or "")

            row = {
                "日志ID": log_response.id,
                "转化ID": log_response.conversion_id if log_response.conversion_id else "已扣量",
                "点击ID": log_response.click_id or "",
                "广告主": log_response.advertiser_name or "",
                "Offer": log_response.offer_name or "",
                "渠道": log_response.publisher_name or "",
                "扣减策略": strategy_label,
                "原始数量": log_response.original_volume or 0,
                "扣减数量": log_response.deducted_volume or 0,
                "最终数量": log_response.final_volume or 0,
                "扣量比例": f"{(log_response.volume_deduction_ratio or 0) * 100:.2f}%",
                "原始金额": f"${log_response.original_amount or 0:.2f}",
                "扣减金额": f"${log_response.deducted_amount or 0:.2f}",
                "最终金额": f"${log_response.final_amount or 0:.2f}",
                "扣金额比例": f"{(log_response.amount_deduction_ratio or 0) * 100:.2f}%",
                "扣减原因": log_response.deduction_reason or "",
                "创建时间": str(log_response.created_at) if log_response.created_at else ""
            }
            data.append(row)

        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df = pd.DataFrame(data)
            df.to_excel(writer, index=False, sheet_name="扣减日志")

            # 设置列宽自适应
            worksheet = writer.sheets["扣减日志"]
            for column_cells in worksheet.columns:
                max_length = max(len(str(cell.value)) for cell in column_cells) if column_cells else 0
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 2, 50)

        output.seek(0)
        filename = f"扣减日志_{get_app_now_naive().strftime('%Y%m%d_%H%M%S')}.xlsx"
        encoded_filename = quote(filename.encode('utf-8'))

        logger.info(f"扣减日志导出成功: 用户={current_user.username}, 数量={len(data)}")

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    except Exception as e:
        logger.error(f"导出扣减日志失败: {str(e)}", exc_info=True)
        if isinstance(e, type(raise_api_exception)):
            raise
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"导出扣减日志失败: {str(e)}"
        )
