"""
统一 Postback 服务接口
支持多平台的 postback 回调处理
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Request, Query, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_

from app.core.database import get_db
from app.core.postback import PostbackProcessor, register_handler
from app.core.postback.macan_handler import MacanPostbackHandler
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.models.models import PostbackConversion, Product, Client
from app.schemas.postback import (
    PostbackRequest,
    PostbackResponse,
    PostbackConversionResponse,
    PostbackStatsResponse,
    PostbackQueryParams
)
from app.schemas.base import ResponseBaseSchema
from app.core.security import get_current_user
from app.models.models import User, UserRole

# 创建路由实例
router = APIRouter()
logger = logging.getLogger(__name__)

# 注册 Macan 处理器
macan_handler = MacanPostbackHandler()
register_handler(macan_handler)


def get_client_ip(request: Request) -> Optional[str]:
    """获取客户端IP地址"""
    # 优先从 X-Forwarded-For 获取（代理服务器）
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For 可能包含多个IP，取第一个
        return forwarded_for.split(",")[0].strip()
    
    # 从 X-Real-IP 获取
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # 最后从客户端直接IP获取
    if request.client:
        return request.client.host
    
    return None


# ====== 查询接口（必须在动态路径之前定义） ======
@router.get("/postback/conversions", 
            response_model=ResponseBaseSchema[list[PostbackConversionResponse]],
            summary="查询 PostBack 转化记录（管理员）")
async def get_postback_conversions(
    request: Request,
    platform: Optional[str] = Query(None, description="平台名称"),
    product_id: Optional[int] = Query(None, description="产品ID"),
    client_id: Optional[int] = Query(None, description="客户ID"),
    event_name: Optional[str] = Query(None, description="事件名称"),
    start_date: Optional[str] = Query(None, description="起始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    查询 PostBack 转化记录（仅管理员）
    """
    # 检查权限（仅管理员）
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(
            ErrorCode.FORBIDDEN,
            detail="仅管理员可查询 PostBack 转化记录"
        )
    
    try:
        # 构建查询
        query = select(PostbackConversion)
        
        # 应用过滤条件
        conditions = []
        
        if platform:
            conditions.append(PostbackConversion.platform == platform)
        if product_id:
            conditions.append(PostbackConversion.product_id == product_id)
        if client_id:
            conditions.append(PostbackConversion.client_id == client_id)
        if event_name:
            conditions.append(PostbackConversion.event_name == event_name)
        
        # 日期范围过滤
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
                conditions.append(func.date(PostbackConversion.created_at) >= start_date_obj)
            except ValueError:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="起始日期格式错误，请使用 YYYY-MM-DD 格式"
                )
        
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
                conditions.append(func.date(PostbackConversion.created_at) <= end_date_obj)
            except ValueError:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="结束日期格式错误，请使用 YYYY-MM-DD 格式"
                )
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 计算总数
        count_query = select(func.count()).select_from(PostbackConversion)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页查询
        query = query.order_by(PostbackConversion.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        result = await db.execute(query)
        conversions = result.scalars().all()
        
        # 转换为响应格式
        conversion_list = [
            PostbackConversionResponse.model_validate(conv)
            for conv in conversions
        ]
        
        logger.info(
            f"管理员 {current_user.username} 查询 PostBack 转化记录: "
            f"platform={platform}, total={total}, page={page}, page_size={page_size}"
        )
        
        return ResponseBaseSchema.success(
            data=conversion_list,
            message=f"成功获取 {len(conversion_list)} 条记录，共 {total} 条"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询 PostBack 转化记录失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"查询失败：{str(e)}"
        )


@router.get("/postback/stats",
            response_model=ResponseBaseSchema[list[PostbackStatsResponse]],
            summary="PostBack 统计信息（管理员）")
async def get_postback_stats(
    request: Request,
    platform: Optional[str] = Query(None, description="平台名称"),
    start_date: Optional[str] = Query(None, description="起始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取 PostBack 统计信息（仅管理员）
    """
    # 检查权限（仅管理员）
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(
            ErrorCode.FORBIDDEN,
            detail="仅管理员可查看 PostBack 统计信息"
        )
    
    try:
        # 构建查询
        query = select(
            PostbackConversion.platform,
            func.count(PostbackConversion.id).label("total_conversions"),
            func.sum(PostbackConversion.payout).label("total_payout"),
            func.sum(PostbackConversion.event_value).label("total_event_value"),
            func.count(func.distinct(PostbackConversion.event_name)).label("unique_events")
        )
        
        # 应用过滤条件
        conditions = []
        if platform:
            conditions.append(PostbackConversion.platform == platform)
        
        # 日期范围过滤
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
                conditions.append(func.date(PostbackConversion.created_at) >= start_date_obj)
            except ValueError:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="起始日期格式错误，请使用 YYYY-MM-DD 格式"
                )
        
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
                conditions.append(func.date(PostbackConversion.created_at) <= end_date_obj)
            except ValueError:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="结束日期格式错误，请使用 YYYY-MM-DD 格式"
                )
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 按平台分组
        query = query.group_by(PostbackConversion.platform)
        query = query.order_by(PostbackConversion.platform)
        
        result = await db.execute(query)
        stats_rows = result.all()
        
        # 转换为响应格式
        stats_list = []
        for row in stats_rows:
            stats_list.append(PostbackStatsResponse(
                platform=row.platform,
                total_conversions=int(row.total_conversions or 0),
                total_payout=float(row.total_payout or 0.0),
                total_event_value=float(row.total_event_value or 0.0),
                unique_events=int(row.unique_events or 0),
                date_range={
                    "start": start_date or "",
                    "end": end_date or ""
                } if start_date or end_date else None
            ))
        
        logger.info(
            f"管理员 {current_user.username} 查询 PostBack 统计信息: "
            f"platform={platform}, stats_count={len(stats_list)}"
        )
        
        return ResponseBaseSchema.success(
            data=stats_list,
            message=f"成功获取 {len(stats_list)} 个平台的统计信息"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询 PostBack 统计信息失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"查询失败：{str(e)}"
        )


# ====== Postback 接收接口（动态路径，必须在具体路径之后） ======
# 保留的路径关键字，不能作为平台名称
RESERVED_PATHS = {"conversions", "stats"}

@router.post("/postback/{platform}", response_model=PostbackResponse, summary="接收 PostBack 回调（POST）")
async def receive_postback_post(
    platform: str = Path(..., description="平台名称", regex="^(?!conversions|stats$).+"),
    request: Request,
    postback_data: PostbackRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    接收指定平台的 PostBack 回调（POST 方式）
    
    支持的平台：
    - macan: Macan S2S PostBack
    
    参数说明：
    - platform: 平台名称（路径参数）
    - postback_data: PostBack 数据（请求体）
    """
    # 检查是否为保留路径
    if platform.lower() in RESERVED_PATHS:
        raise_api_exception(
            ErrorCode.NOT_FOUND,
            detail=f"路径 /postback/{platform} 是保留路径，请使用正确的 API 端点"
        )
    
    try:
        # 获取客户端IP
        client_ip = get_client_ip(request)
        
        # 将 Pydantic 模型转换为字典
        raw_data = postback_data.model_dump(exclude_none=False)
        
        # 处理 postback
        result = await PostbackProcessor.process(
            platform=platform.lower(),
            raw_data=raw_data,
            db=db,
            request_ip=client_ip
        )
        
        return PostbackResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理 {platform} postback 时发生错误: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"处理 PostBack 回调失败：{str(e)}"
        )


@router.get("/postback/{platform}", response_model=PostbackResponse, summary="接收 PostBack 回调（GET）")
async def receive_postback_get(
    platform: str = Path(..., description="平台名称", regex="^(?!conversions|stats$).+"),
    request: Request,
    db: AsyncSession = Depends(get_db),
    # 通用参数（通过 Query 接收）
    conversion_id: Optional[str] = Query(None, description="转化ID"),
    event_name: Optional[str] = Query(None, description="事件名称"),
    event_value: Optional[float] = Query(None, description="事件价值"),
    payout: Optional[float] = Query(None, description="支付金额"),
    devad_id: Optional[str] = Query(None, description="设备广告ID"),
    os: Optional[str] = Query(None, description="操作系统"),
    carrier: Optional[str] = Query(None, description="运营商"),
    ip: Optional[str] = Query(None, description="IP地址"),
    gid: Optional[str] = Query(None, description="渠道ID"),
    product_id: Optional[int] = Query(None, description="产品ID"),
    client_id: Optional[int] = Query(None, description="客户ID"),
    # Macan 特定参数（兼容性）
    clk_id: Optional[str] = Query(None, description="Macan click ID（兼容参数）"),
    click_id: Optional[str] = Query(None, description="Click ID（兼容参数）"),
    event_id: Optional[str] = Query(None, description="Event ID（兼容参数）"),
):
    """
    接收指定平台的 PostBack 回调（GET 方式）
    
    支持的平台：
    - macan: Macan S2S PostBack
    
    参数说明：
    - platform: 平台名称（路径参数）
    - 其他参数通过查询字符串传递
    """
    # 检查是否为保留路径
    if platform.lower() in RESERVED_PATHS:
        raise_api_exception(
            ErrorCode.NOT_FOUND,
            detail=f"路径 /postback/{platform} 是保留路径，请使用正确的 API 端点"
        )
    
    try:
        # 获取客户端IP
        client_ip = get_client_ip(request) or ip
        
        # 构建原始数据字典
        raw_data: Dict[str, Any] = {}
        
        # 处理通用参数
        if conversion_id:
            raw_data["conversion_id"] = conversion_id
        if event_name:
            raw_data["event_name"] = event_name
        if event_value is not None:
            raw_data["event_value"] = event_value
        if payout is not None:
            raw_data["payout"] = payout
        if devad_id:
            raw_data["devad_id"] = devad_id
        if os:
            raw_data["os"] = os
        if carrier:
            raw_data["carrier"] = carrier
        if ip:
            raw_data["ip"] = ip
        if gid:
            raw_data["gid"] = gid
        if product_id is not None:
            raw_data["product_id"] = product_id
        if client_id is not None:
            raw_data["client_id"] = client_id
        
        # 处理 Macan 特定参数（兼容性）
        if clk_id:
            raw_data["clk_id"] = clk_id
        if click_id:
            raw_data["click_id"] = click_id
        if event_id:
            raw_data["event_id"] = event_id
        
        # 处理 postback
        result = await PostbackProcessor.process(
            platform=platform.lower(),
            raw_data=raw_data,
            db=db,
            request_ip=client_ip
        )
        
        return PostbackResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理 {platform} postback 时发生错误: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"处理 PostBack 回调失败：{str(e)}"
        )

