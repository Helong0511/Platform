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
    """创建扣减配置（仅管理员）"""
    # 验证至少启用一种扣减方式
    if not config_in.enable_volume_deduction and not config_in.enable_amount_deduction:
        raise_api_exception(
            ErrorCode.INVALID_PARAMETER,
            detail="请至少启用一种扣减方式（扣量或扣金额）"
        )
    
    # 根据层级验证对象是否存在
    if config_in.level == 'advertiser':
        result = await db.execute(
            select(Advertiser).where(Advertiser.id == config_in.target_id)
        )
        advertiser = result.scalars().first()
        if not advertiser:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"广告主ID {config_in.target_id} 不存在"
            )
        # 检查是否已存在激活的配置
        existing = await db.execute(
            select(ConversionDeductionConfig).where(
                and_(
                    ConversionDeductionConfig.advertiser_id == config_in.target_id,
                    ConversionDeductionConfig.is_active == True
                )
            )
        )
        if existing.scalars().first():
            raise_api_exception(
                ErrorCode.RESOURCE_ALREADY_EXISTS,
                detail=f"广告主ID {config_in.target_id} 已存在激活的扣减配置"
            )
    elif config_in.level == 'offer':
        result = await db.execute(
            select(Offer).where(Offer.id == config_in.target_id)
        )
        offer = result.scalars().first()
        if not offer:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Offer ID {config_in.target_id} 不存在"
            )
        existing = await db.execute(
            select(ConversionDeductionConfig).where(
                and_(
                    ConversionDeductionConfig.offer_id == config_in.target_id,
                    ConversionDeductionConfig.is_active == True
                )
            )
        )
        if existing.scalars().first():
            raise_api_exception(
                ErrorCode.RESOURCE_ALREADY_EXISTS,
                detail=f"Offer ID {config_in.target_id} 已存在激活的扣减配置"
            )
    elif config_in.level == 'publisher':
        result = await db.execute(
            select(Publisher).where(Publisher.id == config_in.target_id)
        )
        publisher = result.scalars().first()
        if not publisher:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"渠道ID {config_in.target_id} 不存在"
            )
        existing = await db.execute(
            select(ConversionDeductionConfig).where(
                and_(
                    ConversionDeductionConfig.publisher_id == config_in.target_id,
                    ConversionDeductionConfig.is_active == True
                )
            )
        )
        if existing.scalars().first():
            raise_api_exception(
                ErrorCode.RESOURCE_ALREADY_EXISTS,
                detail=f"渠道ID {config_in.target_id} 已存在激活的扣减配置"
            )
    else:
        raise_api_exception(
            ErrorCode.INVALID_PARAMETER,
            detail=f"无效的配置层级: {config_in.level}"
        )
    
    # 创建配置
    config = ConversionDeductionConfig(
        advertiser_id=config_in.target_id if config_in.level == 'advertiser' else None,
        offer_id=config_in.target_id if config_in.level == 'offer' else None,
        publisher_id=config_in.target_id if config_in.level == 'publisher' else None,
        enable_volume_deduction=config_in.enable_volume_deduction,
        volume_deduction_ratio=config_in.volume_deduction_ratio,
        deduction_strategy=config_in.deduction_strategy,
        enable_amount_deduction=config_in.enable_amount_deduction,
        amount_deduction_ratio=config_in.amount_deduction_ratio,
        priority=config_in.priority,
        is_active=config_in.is_active
    )
    
    try:
        db.add(config)
        await db.commit()
        await db.refresh(config)
        
        # 加载关联信息
        config_data = ConversionDeductionConfigResponse.model_validate(config)
        if config.advertiser:
            config_data.target_name = config.advertiser.advertiser_name
            config_data.advertiser_name = config.advertiser.advertiser_name
        elif config.offer:
            config_data.target_name = config.offer.offer_name
            config_data.offer_name = config.offer.offer_name
        elif config.publisher:
            config_data.target_name = config.publisher.publisher_name
            config_data.publisher_name = config.publisher.publisher_name
        
        logger.info(f"扣减配置创建成功: config_id={config.id}, level={config_in.level}")
        return ResponseBaseSchema.success(data=config_data)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建扣减配置失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建扣减配置失败: {str(e)}"
        )


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
    """获取扣减配置列表"""
    try:
        # 构建查询
        query = select(ConversionDeductionConfig)
        
        # 应用过滤条件
        conditions = []
        if level:
            if level == 'advertiser':
                conditions.append(ConversionDeductionConfig.advertiser_id.isnot(None))
            elif level == 'offer':
                conditions.append(ConversionDeductionConfig.offer_id.isnot(None))
            elif level == 'publisher':
                conditions.append(ConversionDeductionConfig.publisher_id.isnot(None))
        
        if is_active is not None:
            conditions.append(ConversionDeductionConfig.is_active == is_active)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 获取总数
        count_query = select(func.count()).select_from(ConversionDeductionConfig)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页
        query = query.order_by(ConversionDeductionConfig.priority.desc(), ConversionDeductionConfig.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        # 加载关联信息
        query = query.options(
            joinedload(ConversionDeductionConfig.advertiser),
            joinedload(ConversionDeductionConfig.offer),
            joinedload(ConversionDeductionConfig.publisher)
        )
        
        result = await db.execute(query)
        configs = result.unique().scalars().all()
        
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
        
        # 关键词搜索（在内存中过滤，因为需要关联查询）
        if keyword:
            keyword_lower = keyword.lower()
            config_list = [
                c for c in config_list
                if keyword_lower in (c.target_name or '').lower()
            ]
            total = len(config_list)
        
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
    result = await db.execute(
        select(ConversionDeductionConfig).where(ConversionDeductionConfig.id == config_id)
    )
    config = result.scalars().first()
    
    if not config:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"扣减配置ID {config_id} 不存在"
        )
    
    # 更新字段
    update_data = config_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == 'level' or field == 'target_id':
            # 层级和目标ID不能直接更新，需要重新创建
            continue
        setattr(config, field, value)
    
    try:
        await db.commit()
        await db.refresh(config)
        
        # 加载关联信息
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
        
        logger.info(f"扣减配置更新成功: config_id={config_id}")
        return ResponseBaseSchema.success(data=config_data)
    except Exception as e:
        await db.rollback()
        logger.error(f"更新扣减配置失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新扣减配置失败: {str(e)}"
        )


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
    result = await db.execute(
        select(ConversionDeductionConfig).where(ConversionDeductionConfig.id == config_id)
    )
    config = result.scalars().first()
    
    if not config:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"扣减配置ID {config_id} 不存在"
        )
    
    try:
        # 删除配置
        await db.delete(config)
        await db.commit()
        
        logger.info(f"扣减配置删除成功: config_id={config_id}")
        return ResponseBaseSchema.success(data={"id": config_id})
    except Exception as e:
        await db.rollback()
        logger.error(f"删除扣减配置失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除扣减配置失败: {str(e)}"
        )


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
    result = await db.execute(
        select(ConversionDeductionConfig).where(ConversionDeductionConfig.id == config_id)
    )
    config = result.scalars().first()
    
    if not config:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"扣减配置ID {config_id} 不存在"
        )
    
    config.is_active = is_active
    
    try:
        await db.commit()
        
        logger.info(f"扣减配置状态更新成功: config_id={config_id}, is_active={is_active}")
        return ResponseBaseSchema.success(data={"id": config_id, "is_active": is_active})
    except Exception as e:
        await db.rollback()
        logger.error(f"更新扣减配置状态失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新扣减配置状态失败: {str(e)}"
        )


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
    try:
        # 解析日期
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_dt = datetime.now() - timedelta(days=30)
        
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        else:
            end_dt = datetime.now()
        
        # 构建查询条件
        conditions = [
            ConversionDeductionLog.created_at >= start_dt,
            ConversionDeductionLog.created_at < end_dt
        ]
        
        if advertiser_id:
            conditions.append(ConversionDeductionLog.advertiser_id == advertiser_id)
        if offer_id:
            conditions.append(ConversionDeductionLog.offer_id == offer_id)
        if publisher_id:
            conditions.append(ConversionDeductionLog.publisher_id == publisher_id)
        
        # 统计总体数据
        stats_query = select(
            func.sum(ConversionDeductionLog.original_volume).label('original_volume'),
            func.sum(ConversionDeductionLog.deducted_volume).label('deducted_volume'),
            func.sum(ConversionDeductionLog.final_volume).label('final_volume'),
            func.sum(ConversionDeductionLog.original_amount).label('original_amount'),
            func.sum(ConversionDeductionLog.deducted_amount).label('deducted_amount'),
            func.sum(ConversionDeductionLog.final_amount).label('final_amount')
        ).where(and_(*conditions))
        
        stats_result = await db.execute(stats_query)
        stats_row = stats_result.first()
        
        original_volume = stats_row.original_volume or 0
        deducted_volume = stats_row.deducted_volume or 0
        final_volume = stats_row.final_volume or 0
        original_amount = float(stats_row.original_amount or 0)
        deducted_amount = float(stats_row.deducted_amount or 0)
        final_amount = float(stats_row.final_amount or 0)
        
        # 计算比例
        volume_deduction_ratio = deducted_volume / original_volume if original_volume > 0 else 0.0
        amount_deduction_ratio = deducted_amount / original_amount if original_amount > 0 else 0.0
        
        # 分组统计（简化版，实际可以根据group_by参数进行更复杂的分组）
        items = []  # 这里可以根据group_by参数实现分组统计
        
        stats = DeductionStatsResponse(
            original_volume=int(original_volume),
            deducted_volume=int(deducted_volume),
            final_volume=int(final_volume),
            volume_deduction_ratio=volume_deduction_ratio,
            original_amount=original_amount,
            deducted_amount=deducted_amount,
            final_amount=final_amount,
            amount_deduction_ratio=amount_deduction_ratio,
            items=items
        )
        
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
    """获取扣减日志（仅管理员）"""
    try:
        # 解析日期
        conditions = []
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            conditions.append(ConversionDeductionLog.created_at >= start_dt)
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            conditions.append(ConversionDeductionLog.created_at < end_dt)
        
        if advertiser_id:
            conditions.append(ConversionDeductionLog.advertiser_id == advertiser_id)
        if offer_id:
            conditions.append(ConversionDeductionLog.offer_id == offer_id)
        if publisher_id:
            conditions.append(ConversionDeductionLog.publisher_id == publisher_id)
        
        # 获取总数
        count_query = select(func.count()).select_from(ConversionDeductionLog)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页查询
        query = select(ConversionDeductionLog)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(ConversionDeductionLog.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        # 加载关联信息
        query = query.options(
            joinedload(ConversionDeductionLog.advertiser),
            joinedload(ConversionDeductionLog.offer),
            joinedload(ConversionDeductionLog.publisher)
        )
        
        result = await db.execute(query)
        logs = result.unique().scalars().all()
        
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

