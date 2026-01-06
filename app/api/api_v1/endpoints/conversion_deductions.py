"""
转化扣减配置管理 API
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.constants import MAX_PAGE_SIZE
from app.models.models import (
    User, 
    ConversionDeductionConfig, 
    ConversionDeductionLog,
    Advertiser,
    Offer,
    Publisher,
    PostbackConversion
)
from app.schemas.cpl.deduction import (
    ConversionDeductionConfigCreate,
    ConversionDeductionConfigUpdate,
    ConversionDeductionConfigResponse,
    ConversionDeductionLogResponse,
    DeductionStatsResponse
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/",
             response_model=ResponseBaseSchema[ConversionDeductionConfigResponse],
             summary="创建扣减配置",
             dependencies=[Depends(require_admin)])
async def create_deduction_config(
    config_in: ConversionDeductionConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建扣减配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在ConversionDeductionService中）
    from app.core.dependencies import get_conversion_deduction_service
    from app.services.cpl.conversion_deduction_service import ConversionDeductionService
    
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)
    
    # 准备扣减配置数据
    config_data = config_in.model_dump()
    
    # 调用服务层创建扣减配置（服务层会处理所有验证）
    config = await deduction_service.create_deduction_config(config_data, current_user)
    
    # 构建响应数据
    config_response = ConversionDeductionConfigResponse.model_validate(config)
    if config.advertiser:
        config_response.target_name = config.advertiser.advertiser_name
        config_response.advertiser_name = config.advertiser.advertiser_name
        config_response.level = 'advertiser'
        config_response.target_id = config.advertiser_id
    elif config.offer:
        config_response.target_name = config.offer.offer_name
        config_response.offer_name = config.offer.offer_name
        config_response.level = 'offer'
        config_response.target_id = config.offer_id
    elif config.publisher:
        config_response.target_name = config.publisher.publisher_name
        config_response.publisher_name = config.publisher.publisher_name
        config_response.level = 'publisher'
        config_response.target_id = config.publisher_id
    
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取扣减配置列表（已重构使用服务层）"""
    # 使用服务层（业务逻辑在ConversionDeductionService中）
    from app.core.dependencies import get_conversion_deduction_service
    from app.services.cpl.conversion_deduction_service import ConversionDeductionService
    
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)
    
    try:
        # 调用服务层获取扣减配置列表（服务层会处理查询、过滤、分页、搜索）
        configs, total = await deduction_service.get_deduction_configs(
            page=page,
            page_size=page_size,
            level=level,
            is_active=is_active,
            keyword=keyword
        )
        
        # 转换为响应格式
        config_list = []
        for config in configs:
            config_data = ConversionDeductionConfigResponse.model_validate(config)
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
            config_list.append(config_data)
        
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
    """更新扣减配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在ConversionDeductionService中）
    from app.core.dependencies import get_conversion_deduction_service
    from app.services.cpl.conversion_deduction_service import ConversionDeductionService
    
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)
    
    # 准备更新数据
    update_data = config_in.model_dump(exclude_unset=True)
    
    # 调用服务层更新扣减配置（服务层会处理所有验证和逻辑）
    config = await deduction_service.update_deduction_config(config_id, update_data, current_user)
    
    # 构建响应数据
    config_data = ConversionDeductionConfigResponse.model_validate(config)
    if config.advertiser:
        config_data.target_name = config.advertiser.advertiser_name
        config_data.level = 'advertiser'
        config_data.target_id = config.advertiser_id
    elif config.offer:
        config_data.target_name = config.offer.offer_name
        config_data.level = 'offer'
        config_data.target_id = config.offer_id
    elif config.publisher:
        config_data.target_name = config.publisher.publisher_name
        config_data.level = 'publisher'
        config_data.target_id = config.publisher_id
    
    return ResponseBaseSchema.success(data=config_data)


@router.delete("/{config_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除扣减配置",
               dependencies=[Depends(require_admin)])
async def delete_deduction_config(
    config_id: int = Path(..., ge=1, description="配置ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除扣减配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在ConversionDeductionService中）
    from app.core.dependencies import get_conversion_deduction_service
    from app.services.cpl.conversion_deduction_service import ConversionDeductionService
    
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)
    
    # 调用服务层删除扣减配置（服务层会处理验证和删除）
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
    """更新扣减配置状态（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在ConversionDeductionService中）
    from app.core.dependencies import get_conversion_deduction_service
    from app.services.cpl.conversion_deduction_service import ConversionDeductionService
    
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)
    
    # 调用服务层更新扣减配置状态（服务层会处理验证和更新）
    await deduction_service.update_deduction_config_status(config_id, is_active, current_user)
    
    return ResponseBaseSchema.success(data={"id": config_id, "is_active": is_active})


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
    """获取扣减统计（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在ConversionDeductionService中）
    from app.core.dependencies import get_conversion_deduction_service
    from app.services.cpl.conversion_deduction_service import ConversionDeductionService
    
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)
    
    try:
        # 调用服务层获取扣减统计（服务层会处理查询和计算）
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取扣减日志（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在ConversionDeductionService中）
    from app.core.dependencies import get_conversion_deduction_service
    from app.services.cpl.conversion_deduction_service import ConversionDeductionService
    
    deduction_service: ConversionDeductionService = await get_conversion_deduction_service(db)
    
    try:
        # 调用服务层获取扣减日志（服务层会处理查询、过滤、分页）
        logs, total = await deduction_service.get_deduction_logs(
            page=page,
            page_size=page_size,
            start_date=start_date,
            end_date=end_date,
            advertiser_id=advertiser_id,
            offer_id=offer_id,
            publisher_id=publisher_id
        )
        
        # 转换为响应格式
        log_list = []
        for log in logs:
            log_data = ConversionDeductionLogResponse.model_validate(log)
            if log.advertiser:
                log_data.advertiser_name = log.advertiser.advertiser_name
            if log.offer:
                log_data.offer_name = log.offer.offer_name
            if log.publisher:
                log_data.publisher_name = log.publisher.publisher_name
            log_list.append(log_data)
        
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

