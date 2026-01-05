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
from app.core.postback.bft_handler import BftPostbackHandler
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.constants import MAX_PAGE_SIZE
from app.core.utils import parse_date_to_app_timezone
from app.models.models import PostbackConversion, Product, Client, PostbackForwardLog, PostbackNotification, Click, Offer, Publisher, Advertiser
from app.schemas.postback import (
    PostbackRequest,
    PostbackResponse,
    PostbackConversionResponse,
    PostbackStatsResponse,
    PostbackQueryParams,
    PostbackForwardLogResponse
)
from app.schemas.base import ResponseBaseSchema
from app.core.security import get_current_user
from app.models.models import User, UserRole

# 创建路由实例
router = APIRouter()
logger = logging.getLogger(__name__)

# 注册 BFT 处理器
bft_handler = BftPostbackHandler()
register_handler(bft_handler)


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
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页数量"),
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
        
        # 日期范围过滤（使用应用时区，与数据库时间一致）
        if start_date:
            try:
                start_datetime = parse_date_to_app_timezone(start_date, is_end_date=False)
                conditions.append(PostbackConversion.created_at >= start_datetime)
            except ValueError:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="起始日期格式错误，请使用 YYYY-MM-DD 格式"
                )
        
        if end_date:
            try:
                end_datetime = parse_date_to_app_timezone(end_date, is_end_date=True)
                conditions.append(PostbackConversion.created_at <= end_datetime)
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
        
        # 批量查询通知记录数量
        conversion_ids = [conv.id for conv in conversions]
        notification_counts = {}
        if conversion_ids:
            notification_query = select(
                PostbackNotification.conversion_id,
                func.count(PostbackNotification.id).label('count')
            ).where(
                PostbackNotification.conversion_id.in_(conversion_ids)
            ).group_by(PostbackNotification.conversion_id)
            
            notification_result = await db.execute(notification_query)
            for row in notification_result.all():
                notification_counts[row.conversion_id] = row.count
        
        # 批量查询产品和客户信息
        product_ids = list(set([conv.product_id for conv in conversions if conv.product_id]))
        client_ids = list(set([conv.client_id for conv in conversions if conv.client_id]))
        
        products_map = {}
        if product_ids:
            products_query = select(Product.id, Product.name).where(Product.id.in_(product_ids))
            products_result = await db.execute(products_query)
            for row in products_result.all():
                products_map[row.id] = row.name
        
        clients_map = {}
        if client_ids:
            clients_query = select(Client.id, Client.company_name, Client.user_id).where(Client.id.in_(client_ids))
            clients_result = await db.execute(clients_query)
            # 获取用户信息以显示客户名称
            # 先收集所有需要查询的用户ID
            clients_result_temp = await db.execute(clients_query)
            user_ids = list(set([row.user_id for row in clients_result_temp.all() if row.user_id]))
            users_map = {}
            if user_ids:
                users_query = select(User.id, User.full_name, User.username).where(User.id.in_(user_ids))
                users_result = await db.execute(users_query)
                for row in users_result.all():
                    users_map[row.id] = row.full_name or row.username
            
            # 重新查询客户（因为上面的查询结果已经被消费）
            clients_result = await db.execute(clients_query)
            for row in clients_result.all():
                # 优先使用公司名称，如果没有则使用用户全名
                client_name = row.company_name
                if not client_name and row.user_id and row.user_id in users_map:
                    client_name = users_map[row.user_id]
                if not client_name:
                    client_name = f"客户_{row.id}"
                clients_map[row.id] = client_name
        
        # 批量查询点击记录信息（通过 conversion_id = clicks.click_id 关联）
        conversion_ids = list(set([conv.conversion_id for conv in conversions if conv.conversion_id]))
        clicks_map = {}
        offer_ids = set()
        publisher_ids = set()
        advertiser_ids = set()
        gid_publisher_ids = set()  # 通过 gid 关联的渠道ID
        
        if conversion_ids:
            clicks_query = select(
                Click.click_id,
                Click.offer_id,
                Click.publisher_id,
                Click.advertiser_id,
                Click.click_time
            ).where(Click.click_id.in_(conversion_ids))
            clicks_result = await db.execute(clicks_query)
            for row in clicks_result.all():
                clicks_map[row.click_id] = {
                    'offer_id': row.offer_id,
                    'publisher_id': row.publisher_id,
                    'advertiser_id': row.advertiser_id,
                    'click_time': row.click_time
                }
                if row.offer_id:
                    offer_ids.add(row.offer_id)
                if row.publisher_id:
                    publisher_ids.add(row.publisher_id)
                if row.advertiser_id:
                    advertiser_ids.add(row.advertiser_id)
        
        # 通过 gid 字段关联渠道（gid 是渠道ID）
        for conv in conversions:
            if conv.gid:
                try:
                    # gid 可能是字符串格式的渠道ID，尝试转换为整数
                    gid_int = int(conv.gid)
                    gid_publisher_ids.add(gid_int)
                except (ValueError, TypeError):
                    # 如果转换失败，跳过
                    pass
        
        # 批量查询 Offer、Publisher、Advertiser 信息
        offers_map = {}
        if offer_ids:
            offers_query = select(Offer.id, Offer.offer_name).where(Offer.id.in_(list(offer_ids)))
            offers_result = await db.execute(offers_query)
            for row in offers_result.all():
                offers_map[row.id] = row.offer_name
        
        # 合并通过点击记录和 gid 获取的渠道ID
        all_publisher_ids = list(publisher_ids | gid_publisher_ids)
        publishers_map = {}
        if all_publisher_ids:
            publishers_query = select(Publisher.id, Publisher.publisher_name).where(Publisher.id.in_(all_publisher_ids))
            publishers_result = await db.execute(publishers_query)
            for row in publishers_result.all():
                publishers_map[row.id] = row.publisher_name
        
        advertisers_map = {}
        if advertiser_ids:
            advertisers_query = select(Advertiser.id, Advertiser.advertiser_name).where(Advertiser.id.in_(list(advertiser_ids)))
            advertisers_result = await db.execute(advertisers_query)
            for row in advertisers_result.all():
                advertisers_map[row.id] = row.advertiser_name
        
        # 转换为响应格式，并添加关联信息
        conversion_list = []
        for conv in conversions:
            conv_dict = PostbackConversionResponse.model_validate(conv).model_dump()
            conv_dict['notification_count'] = notification_counts.get(conv.id, 0)
            # 添加产品名称
            if conv.product_id and conv.product_id in products_map:
                conv_dict['product_name'] = products_map[conv.product_id]
            # 添加客户名称
            if conv.client_id and conv.client_id in clients_map:
                conv_dict['client_name'] = clients_map[conv.client_id]
            
            # 通过 conversion_id = clicks.click_id 关联点击记录
            if conv.conversion_id and conv.conversion_id in clicks_map:
                click_info = clicks_map[conv.conversion_id]
                conv_dict['click_id'] = conv.conversion_id  # conversion_id 就是 click_id
                conv_dict['click_offer_id'] = click_info['offer_id']
                conv_dict['click_publisher_id'] = click_info['publisher_id']
                conv_dict['click_advertiser_id'] = click_info['advertiser_id']
                conv_dict['click_time'] = click_info['click_time']
                # 添加关联名称
                if click_info['offer_id'] and click_info['offer_id'] in offers_map:
                    conv_dict['click_offer_name'] = offers_map[click_info['offer_id']]
                if click_info['publisher_id'] and click_info['publisher_id'] in publishers_map:
                    conv_dict['click_publisher_name'] = publishers_map[click_info['publisher_id']]
                if click_info['advertiser_id'] and click_info['advertiser_id'] in advertisers_map:
                    conv_dict['click_advertiser_name'] = advertisers_map[click_info['advertiser_id']]
            
            # 通过 gid 关联渠道（gid 是渠道ID）
            if conv.gid:
                try:
                    gid_int = int(conv.gid)
                    if gid_int in publishers_map:
                        # 如果点击记录中没有渠道信息，使用 gid 关联的渠道
                        if not conv_dict.get('click_publisher_id'):
                            conv_dict['click_publisher_id'] = gid_int
                            conv_dict['click_publisher_name'] = publishers_map[gid_int]
                        # 如果点击记录中已有渠道信息，也添加 gid 渠道信息（作为补充）
                        conv_dict['gid_publisher_id'] = gid_int
                        conv_dict['gid_publisher_name'] = publishers_map[gid_int]
                except (ValueError, TypeError):
                    pass
            
            conversion_list.append(conv_dict)
        
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
            func.sum(PostbackConversion.original_payout).label("total_original_payout"),
            func.sum(PostbackConversion.payout).label("total_payout"),
            func.sum(PostbackConversion.event_value).label("total_event_value"),
            func.count(func.distinct(PostbackConversion.event_name)).label("unique_events")
        )
        
        # 应用过滤条件
        conditions = []
        if platform:
            conditions.append(PostbackConversion.platform == platform)
        
        # 日期范围过滤（使用应用时区，与数据库时间一致）
        if start_date:
            try:
                start_datetime = parse_date_to_app_timezone(start_date, is_end_date=False)
                conditions.append(PostbackConversion.created_at >= start_datetime)
            except ValueError:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="起始日期格式错误，请使用 YYYY-MM-DD 格式"
                )
        
        if end_date:
            try:
                end_datetime = parse_date_to_app_timezone(end_date, is_end_date=True)
                conditions.append(PostbackConversion.created_at <= end_datetime)
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
                total_original_payout=float(row.total_original_payout or 0.0) if hasattr(row, 'total_original_payout') else None,
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


# ====== 转发日志查询接口（必须在动态路径之前定义） ======
@router.get("/postback/forward-logs",
            response_model=ResponseBaseSchema[list[PostbackForwardLogResponse]],
            summary="查询 PostBack 下游转发日志（管理员）")
async def get_postback_forward_logs(
    request: Request,
    conversion_id: Optional[int] = Query(None, description="转化记录ID"),
    product_id: Optional[int] = Query(None, description="产品ID"),
    publisher_id: Optional[int] = Query(None, description="渠道ID"),
    success: Optional[bool] = Query(None, description="是否成功"),
    start_date: Optional[str] = Query(None, description="起始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    查询 PostBack 下游转发日志
    
    仅管理员可访问
    """
    # 检查管理员权限
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(
            ErrorCode.FORBIDDEN,
            detail="仅管理员可访问此接口"
        )
    
    try:
        # 构建查询条件
        conditions = []
        
        if conversion_id:
            conditions.append(PostbackForwardLog.conversion_id == conversion_id)
        if product_id:
            conditions.append(PostbackForwardLog.product_id == product_id)
        if publisher_id:
            conditions.append(PostbackForwardLog.publisher_id == publisher_id)
        if success is not None:
            conditions.append(PostbackForwardLog.success == success)
        
        # 日期范围过滤（使用应用时区，与数据库时间一致）
        if start_date:
            try:
                start_dt = parse_date_to_app_timezone(start_date, is_end_date=False)
                conditions.append(PostbackForwardLog.created_at >= start_dt)
            except ValueError:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="起始日期格式错误，应为 YYYY-MM-DD"
                )
        
        if end_date:
            try:
                end_dt = parse_date_to_app_timezone(end_date, is_end_date=True)
                # 结束日期已包含整天（23:59:59.999999）
                from datetime import timedelta
                end_dt = end_dt + timedelta(days=1)
                conditions.append(PostbackForwardLog.created_at < end_dt)
            except ValueError:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="结束日期格式错误，应为 YYYY-MM-DD"
                )
        
        # 构建查询
        query = select(PostbackForwardLog)
        if conditions:
            query = query.where(and_(*conditions))
        
        # 按创建时间倒序排列
        query = query.order_by(PostbackForwardLog.created_at.desc())
        
        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        
        # 执行查询
        result = await db.execute(query)
        logs = result.scalars().all()
        
        # 获取总数
        count_query = select(func.count()).select_from(PostbackForwardLog)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0
        
        return ResponseBaseSchema(
            code=200,
            message="查询成功",
            data=[PostbackForwardLogResponse.model_validate(log) for log in logs],
            total=total,
            page=page,
            page_size=page_size
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询 PostBack 转发日志失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"查询失败：{str(e)}"
        )


# ====== 补发转发接口 ======
@router.post("/postback/forward-logs/{forward_log_id}/resend",
            response_model=ResponseBaseSchema[dict],
            summary="补发 PostBack 转发（管理员）")
async def resend_postback_forward(
    forward_log_id: int = Path(..., ge=1, description="转发日志ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    补发 PostBack 转发
    
    根据转发日志重新发送转发请求，用于处理转发失败的情况
    仅管理员可访问
    """
    from app.core.postback.forwarder import PostbackForwarder
    
    # 检查管理员权限
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(
            ErrorCode.FORBIDDEN,
            detail="仅管理员可访问此接口"
        )
    
    try:
        # 查询转发日志
        result = await db.execute(
            select(PostbackForwardLog).where(PostbackForwardLog.id == forward_log_id)
        )
        forward_log = result.scalars().first()
        
        if not forward_log:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"转发日志ID {forward_log_id} 不存在"
            )
        
        # 查询转化记录
        conversion_result = await db.execute(
            select(PostbackConversion).where(PostbackConversion.id == forward_log.conversion_id)
        )
        conversion = conversion_result.scalars().first()
        
        if not conversion:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"转化记录ID {forward_log.conversion_id} 不存在"
            )
        
        # 根据转发类型重新发送
        if forward_log.publisher_id:
            # 转发到渠道
            await PostbackForwarder.forward_to_publisher(conversion, db)
            message = f"已补发转发到渠道（Publisher ID: {forward_log.publisher_id}）"
        elif forward_log.product_id:
            # 转发到产品下游
            product_result = await db.execute(
                select(Product).where(Product.id == forward_log.product_id)
            )
            product = product_result.scalars().first()
            if product:
                await PostbackForwarder.forward_to_downstream(conversion, product, db)
                message = f"已补发转发到产品下游（Product ID: {forward_log.product_id}）"
            else:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"产品ID {forward_log.product_id} 不存在"
                )
        else:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="转发日志缺少 publisher_id 或 product_id，无法确定转发目标"
            )
        
        logger.info(
            f"用户 {current_user.id} 补发转发: forward_log_id={forward_log_id}, "
            f"conversion_id={forward_log.conversion_id}"
        )
        
        return ResponseBaseSchema.success(
            data={
                "message": message,
                "forward_log_id": forward_log_id,
                "conversion_id": forward_log.conversion_id
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"补发转发失败: forward_log_id={forward_log_id}, error={str(e)}",
            exc_info=True
        )
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"补发转发失败: {str(e)}"
        )


# ====== Postback 接收接口（动态路径，必须在具体路径之后） ======
# 保留的路径关键字，不能作为平台名称
RESERVED_PATHS = {"conversions", "stats", "forward-logs"}

@router.post("/postback/{platform}", response_model=PostbackResponse, summary="接收 PostBack 回调（POST）")
async def receive_postback_post(
    platform: str,
    request: Request,
    postback_data: PostbackRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    接收指定平台的 PostBack 回调（POST 方式）
    
    支持的平台：
    - bft: BFT S2S PostBack
    
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
    platform: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    # 通用参数（通过 Query 接收）
    conversion_id: Optional[str] = Query(None, description="转化ID"),
    event_name: Optional[str] = Query(None, description="事件名称"),
    event_value: Optional[str] = Query(None, description="事件价值（字符串格式，会自动转换为浮点数）"),
    payout: Optional[str] = Query(None, description="支付金额（字符串格式，会自动转换为浮点数）"),
    devad_id: Optional[str] = Query(None, description="设备广告ID"),
    os: Optional[str] = Query(None, description="操作系统"),
    carrier: Optional[str] = Query(None, description="运营商"),
    ip: Optional[str] = Query(None, description="IP地址"),
    gid: Optional[str] = Query(None, description="渠道ID"),
    product_id: Optional[str] = Query(None, description="产品ID（字符串格式，会自动转换为整数）"),
    client_id: Optional[str] = Query(None, description="客户ID（字符串格式，会自动转换为整数）"),
    # Macan 特定参数（兼容性）
    clk_id: Optional[str] = Query(None, description="Macan click ID（兼容参数）"),
    click_id: Optional[str] = Query(None, description="Click ID（兼容参数）"),
    event_id: Optional[str] = Query(None, description="Event ID（兼容参数）"),
):
    """
    接收指定平台的 PostBack 回调（GET 方式）
    
    支持的平台：
    - bft: BFT S2S PostBack
    
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
        # 辅助函数：安全地将字符串转换为浮点数
        def _to_float(value: Optional[str]) -> Optional[float]:
            """将字符串安全地转换为浮点数，处理占位符和无效值"""
            if value is None or value == "":
                return None
            # 如果是占位符格式（如 {event_value}），返回 None
            if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
                return None
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        
        # 辅助函数：安全地将字符串转换为整数
        def _to_int(value: Optional[str]) -> Optional[int]:
            """将字符串安全地转换为整数，处理占位符和无效值"""
            if value is None or value == "":
                return None
            # 如果是占位符格式（如 {product_id}），返回 None
            if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
                return None
            try:
                return int(value)
            except (ValueError, TypeError):
                return None
        
        # 获取客户端IP
        client_ip = get_client_ip(request) or ip
        
        # 构建原始数据字典
        raw_data: Dict[str, Any] = {}
        
        # 处理通用参数
        if conversion_id:
            raw_data["conversion_id"] = conversion_id
        if event_name:
            raw_data["event_name"] = event_name
        event_value_float = _to_float(event_value)
        if event_value_float is not None:
            raw_data["event_value"] = event_value_float
        
        # 处理 payout（支持多种字段名：payout, PayOut, pay_out 等）
        payout_float = _to_float(payout)
        if payout_float is None:
            # 尝试从查询参数中获取其他字段名
            query_params = dict(request.query_params)
            payout_float = (
                _to_float(query_params.get("PayOut")) or
                _to_float(query_params.get("pay_out")) or
                _to_float(query_params.get("pay-out")) or
                _to_float(query_params.get("Pay_Out")) or
                _to_float(query_params.get("Payout")) or
                _to_float(query_params.get("PAYOUT"))
            )
        if payout_float is not None:
            raw_data["payout"] = payout_float
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
        product_id_int = _to_int(product_id)
        if product_id_int is not None:
            raw_data["product_id"] = product_id_int
        client_id_int = _to_int(client_id)
        if client_id_int is not None:
            raw_data["client_id"] = client_id_int
        
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

