"""
统一 Postback 服务接口
支持多平台的 postback 回调处理

功能说明：
- 接收和处理来自上游平台的 postback 回调
- 查询和管理转化记录（已融合转化日志功能）
- 支持多维度筛选：平台、产品、客户、Click ID、Offer、渠道、广告主、转化状态等
- 提供转化统计、转发日志、诊断工具等功能
- 支持更新转化状态（Approved/Pending）

注意：
- 转化日志功能已融合到此模块，原 /api/v1/conversion-logs 接口已废弃
- 建议使用 /api/v1/postback/conversions 接口进行所有转化记录查询
"""
import logging
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Query, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_

from app.core.database import get_db
from app.core.postback import register_handler, PostbackForwarder
from app.core.postback.bft_handler import BftPostbackHandler
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.constants import MAX_PAGE_SIZE
from app.core.utils import parse_date_to_app_timezone
from app.models.models import (
    OfferPublisherAssignment,
    PostbackConversion, Product, Client, PostbackForwardLog, PostbackNotification, 
    Click, ClickStats, Offer, Publisher, Advertiser, User, ConversionDeductionLog
)
from app.schemas.postback import (
    PostbackConversionResponse,
    PostbackStatsResponse,
    PostbackForwardLogResponse
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.core.security import require_admin

# 创建路由实例
router = APIRouter()
logger = logging.getLogger(__name__)

# 注册 BFT 处理器
bft_handler = BftPostbackHandler()
register_handler(bft_handler)


# ====== 查询接口（必须在动态路径之前定义） ======
@router.get("/postback/conversions", 
            response_model=PaginatedResponseBaseSchema[list[PostbackConversionResponse]],
            summary="查询 PostBack 转化记录（管理员，已融合转化日志功能）")
async def get_postback_conversions(
    request: Request,
    platform: Optional[str] = Query(None, description="平台名称"),
    product_id: Optional[int] = Query(None, description="产品ID"),
    client_id: Optional[int] = Query(None, description="客户ID"),
    conversion_or_click_id: Optional[str] = Query(None, description="转化ID或点击ID"),
    # 转化日志筛选条件（融合功能）
    click_id: Optional[str] = Query(None, description="Click ID过滤"),
    offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
    publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
    advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
    conversion_status: Optional[str] = Query(None, description="转化状态过滤（Pending/Approved/CapReached/OfferInactive/ClickExpired）"),
    start_date: Optional[str] = Query(None, description="起始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    查询 PostBack 转化记录（仅管理员）
    已融合转化日志功能，支持所有筛选条件
    """
    
    try:
        # 判断是否需要 JOIN ClickStats 表（用于筛选 offer_id、publisher_id、advertiser_id）
        need_join_click_stats = offer_id is not None or publisher_id is not None or advertiser_id is not None
        
        # 构建查询
        if need_join_click_stats:
            query = select(PostbackConversion).join(ClickStats, PostbackConversion.click_id == ClickStats.click_id)
        else:
            query = select(PostbackConversion)
        
        # 应用过滤条件
        conditions = []
        
        if platform:
            conditions.append(PostbackConversion.platform == platform)
        if product_id:
            conditions.append(PostbackConversion.product_id == product_id)
        if client_id:
            conditions.append(PostbackConversion.client_id == client_id)
        if conversion_or_click_id:
            # 使用OR条件查询conversion_id或click_id
            conditions.append(
                or_(
                    PostbackConversion.conversion_id == conversion_or_click_id,
                    PostbackConversion.click_id == conversion_or_click_id
                )
            )
        # 转化日志筛选条件
        if click_id:
            conditions.append(PostbackConversion.click_id == click_id)
        if offer_id:
            conditions.append(ClickStats.offer_id == offer_id)
        if publisher_id:
            conditions.append(ClickStats.publisher_id == publisher_id)
        if advertiser_id:
            conditions.append(ClickStats.advertiser_id == advertiser_id)
        if conversion_status:
            if hasattr(PostbackConversion, 'conversion_status'):
                conditions.append(PostbackConversion.conversion_status == conversion_status)
        
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
        if need_join_click_stats:
            count_query = select(func.count(PostbackConversion.id)).select_from(
                PostbackConversion.__table__.join(ClickStats.__table__, PostbackConversion.click_id == ClickStats.click_id)
            )
        else:
            count_query = select(func.count(PostbackConversion.id)).select_from(PostbackConversion.__table__)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页查询
        query = query.order_by(PostbackConversion.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        result = await db.execute(query)
        conversions = result.scalars().all()
        
        # 如果使用 conversion_or_click_id 查询且主表没有结果，尝试查询扣减日志表
        # 这样可以找到被扣量而未保存到主表的转化记录
        deduction_logs = []
        if conversion_or_click_id and len(conversions) == 0:
            deduction_query = select(ConversionDeductionLog).where(
                ConversionDeductionLog.click_id == conversion_or_click_id
            )
            if start_date:
                try:
                    start_datetime = parse_date_to_app_timezone(start_date, is_end_date=False)
                    deduction_query = deduction_query.where(ConversionDeductionLog.created_at >= start_datetime)
                except ValueError:
                    pass
            if end_date:
                try:
                    end_datetime = parse_date_to_app_timezone(end_date, is_end_date=True)
                    deduction_query = deduction_query.where(ConversionDeductionLog.created_at <= end_datetime)
                except ValueError:
                    pass
            deduction_query = deduction_query.order_by(ConversionDeductionLog.created_at.desc())
            deduction_result = await db.execute(deduction_query)
            deduction_logs = deduction_result.scalars().all()
            
            if deduction_logs:
                logger.info(
                    f"在主表未找到转化记录，但在扣减日志表中找到 {len(deduction_logs)} 条记录: "
                    f"click_id={conversion_or_click_id}"
                )
        
        # 批量查询通知记录数量（只统计成功发送的通知，status='sent'）
        # 注意：只统计有 conversion_id 的通知（汇总通知 conversion_id 为 NULL，不统计）
        conversion_ids = [conv.id for conv in conversions]
        notification_counts = {}
        if conversion_ids:
            notification_query = select(
                PostbackNotification.conversion_id,
                func.count(PostbackNotification.id).label('count')
            ).where(
                and_(
                    PostbackNotification.conversion_id.in_(conversion_ids),
                    PostbackNotification.conversion_id.isnot(None),  # 排除汇总通知
                    PostbackNotification.notification_status == 'sent'
                )
            ).group_by(PostbackNotification.conversion_id)
            
            notification_result = await db.execute(notification_query)
            for row in notification_result.all():
                notification_counts[row.conversion_id] = row.count
        
        # 批量查询产品和客户信息
        # 使用集合推导式去重，提高性能
        product_ids = list({conv.product_id for conv in conversions if conv.product_id})
        client_ids = list({conv.client_id for conv in conversions if conv.client_id})
        
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
            # 获取所有客户数据（一次性获取，避免重复查询）
            clients_data = list(clients_result.all())
            # 收集所有需要查询的用户ID（使用集合去重）
            user_ids = list({row.user_id for row in clients_data if row.user_id})
            users_map = {}
            if user_ids:
                users_query = select(User.id, User.full_name, User.username).where(User.id.in_(user_ids))
                users_result = await db.execute(users_query)
                for row in users_result.all():
                    users_map[row.id] = row.full_name or row.username
            
            # 使用已获取的客户数据（避免重复查询）
            for row in clients_data:
                # 优先使用公司名称，如果没有则使用用户全名
                client_name = row.company_name
                if not client_name and row.user_id and row.user_id in users_map:
                    client_name = users_map[row.user_id]
                if not client_name:
                    client_name = f"客户_{row.id}"
                clients_map[row.id] = client_name
        
        # 批量查询点击记录信息（通过 conversion_id = clicks.click_id 关联）
        # 同时查询 ClickStats 表以获取 CPL 系统关联信息
        # 使用集合去重，提高性能
        conversion_ids = list({conv.conversion_id for conv in conversions if conv.conversion_id})
        click_ids_from_conversions = list({conv.click_id for conv in conversions if conv.click_id})
        clicks_map = {}
        click_stats_map = {}
        offer_ids = set()
        publisher_ids = set()
        advertiser_ids = set()
        gid_publisher_ids = set()  # 通过 gid 关联的渠道ID
        
        # 查询 Click 表（如果存在）
        if conversion_ids:
            try:
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
            except Exception as e:
                logger.debug(f"无法从 Click 表加载数据: {e}")
        
        # 查询 ClickStats 表（CPL 系统，优先使用）
        if click_ids_from_conversions:
            try:
                click_stats_query = select(
                    ClickStats.click_id,
                    ClickStats.offer_id,
                    ClickStats.publisher_id,
                    ClickStats.advertiser_id,
                    ClickStats.click_time
                ).where(ClickStats.click_id.in_(click_ids_from_conversions))
                click_stats_result = await db.execute(click_stats_query)
                for row in click_stats_result.all():
                    click_stats_map[row.click_id] = {
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
            except Exception as e:
                logger.debug(f"无法从 ClickStats 表加载数据: {e}")
        
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
        
        # 批量查询 Offer-渠道分配配置（用于计算实际转发金额，考虑下游PO限制）
        assignments_map = {}  # key: (offer_id, publisher_id), value: affiliate_payout
        if offer_ids and all_publisher_ids:
            assignments_query = select(
                OfferPublisherAssignment.offer_id,
                OfferPublisherAssignment.publisher_id,
                OfferPublisherAssignment.affiliate_payout
            ).where(
                and_(
                    OfferPublisherAssignment.offer_id.in_(list(offer_ids)),
                    OfferPublisherAssignment.publisher_id.in_(all_publisher_ids),
                    OfferPublisherAssignment.is_active == True
                )
            )
            assignments_result = await db.execute(assignments_query)
            for row in assignments_result.all():
                key = (row.offer_id, row.publisher_id)
                assignments_map[key] = row.affiliate_payout
        
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
            
            # 通过 click_id 关联点击记录（优先使用 ClickStats，其次使用 Click）
            click_info = None
            if conv.click_id:
                # 优先使用 ClickStats
                if conv.click_id in click_stats_map:
                    click_info = click_stats_map[conv.click_id]
                elif conv.click_id in clicks_map:
                    click_info = clicks_map[conv.click_id]
            # 如果没有通过 click_id 找到，尝试通过 conversion_id 查找（向后兼容）
            elif conv.conversion_id and conv.conversion_id in clicks_map:
                click_info = clicks_map[conv.conversion_id]
            
            if click_info:
                conv_dict['click_id'] = conv.click_id or conv.conversion_id
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
            
            # 计算实际转发给渠道的金额（考虑下游PO限制）
            # 如果配置了下游PO且上游金额大于下游PO，使用下游PO；否则使用 conversion.payout
            actual_payout = conv_dict.get('payout')  # 默认使用扣后的 payout
            offer_id = conv_dict.get('click_offer_id')
            publisher_id = conv_dict.get('click_publisher_id')
            
            if offer_id and publisher_id:
                assignment_key = (offer_id, publisher_id)
                if assignment_key in assignments_map:
                    affiliate_payout = assignments_map[assignment_key]
                    if affiliate_payout is not None:
                        # 获取上游金额（优先使用 original_payout，其次使用 payout）
                        upstream_amount = conv_dict.get('original_payout')
                        if upstream_amount is None:
                            upstream_amount = conv_dict.get('payout')
                        
                        if upstream_amount is not None and upstream_amount > affiliate_payout:
                            # 上游金额大于下游PO，使用下游PO金额
                            actual_payout = affiliate_payout
                        else:
                            # 上游金额小于或等于下游PO，使用上游金额（即扣后的 payout）
                            actual_payout = conv_dict.get('payout')
            
            # 更新 payout 为实际转发金额
            conv_dict['payout'] = actual_payout
            
            conversion_list.append(conv_dict)
        
        # 如果有扣减日志记录，添加到响应中（作为提示信息）
        message = f"成功获取 {len(conversion_list)} 条记录，共 {total} 条"
        if deduction_logs and len(conversion_list) == 0:
            message += f"。注意：在扣减日志表中找到 {len(deduction_logs)} 条相关记录，这些转化可能因扣量而未保存到主表。"
            # 将扣减日志信息添加到响应中（作为额外信息）
            for log in deduction_logs[:5]:  # 最多显示5条
                logger.info(
                    f"扣减日志记录: click_id={log.click_id}, "
                    f"deducted_volume={log.deducted_volume}, "
                    f"original_amount={log.original_amount}, "
                    f"created_at={log.created_at}"
                )
        
        logger.info(
            f"管理员 {current_user.username} 查询 PostBack 转化记录: "
            f"platform={platform}, total={total}, page={page}, page_size={page_size}, "
            f"deduction_logs_found={len(deduction_logs) if deduction_logs else 0}"
        )
        
        return PaginatedResponseBaseSchema.success(
            data=conversion_list,
            total=total,
            page=page,
            page_size=page_size,
            message=message
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
    current_user: User = Depends(require_admin)
):
    """
    获取 PostBack 统计信息（仅管理员）
    """
    
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
            response_model=PaginatedResponseBaseSchema[list[PostbackForwardLogResponse]],
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
    current_user: User = Depends(require_admin)
):
    """
    查询 PostBack 下游转发日志
    
    仅管理员可访问
    """
    
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
        
        return PaginatedResponseBaseSchema.success(
            data=[PostbackForwardLogResponse.model_validate(log) for log in logs],
            total=total,
            page=page,
            page_size=page_size,
            message="查询成功"
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
    current_user: User = Depends(require_admin)
):
    """
    补发 PostBack 转发
    
    根据转发日志重新发送转发请求，用于处理转发失败的情况
    仅管理员可访问
    """
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
        
        # 根据转发类型重新发送（只支持转发到渠道）
        if forward_log.publisher_id:
            # 转发到渠道
            await PostbackForwarder.forward_to_publisher(conversion, db)
            message = f"已补发转发到渠道（Publisher ID: {forward_log.publisher_id}）"
        elif forward_log.product_id:
            # 产品下游转发已废弃，不再支持
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="产品下游转发功能已废弃，PostBack 数据只转发给渠道（Publisher）"
            )
        else:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="转发日志缺少 publisher_id，无法确定转发目标"
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


# ====== 诊断工具接口 ======
@router.get("/postback/diagnose",
            response_model=ResponseBaseSchema[dict],
            summary="诊断 PostBack 记录问题（管理员）")
async def diagnose_postback_record(
    conversion_or_click_id: str = Query(..., description="转化ID或点击ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    诊断 PostBack 记录问题
    
    当收到通知但找不到记录时，使用此接口进行诊断
    会检查：
    1. 主表（postback_conversions）中是否存在
    2. 扣减日志表（conversion_deduction_logs）中是否存在
    3. 通知记录表（postback_notifications）中是否存在
    4. 可能的平台名称变化
    
    仅管理员可访问
    """
    
    try:
        diagnosis_result = {
            "conversion_or_click_id": conversion_or_click_id,
            "found_in_main_table": False,
            "found_in_deduction_logs": False,
            "found_in_notifications": False,
            "platform_name_changes": [],
            "suggestions": []
        }
        
        # 1. 检查主表（postback_conversions）
        main_table_query = select(PostbackConversion).where(
            or_(
                PostbackConversion.conversion_id == conversion_or_click_id,
                PostbackConversion.click_id == conversion_or_click_id
            )
        )
        main_result = await db.execute(main_table_query)
        main_records = main_result.scalars().all()
        
        if main_records:
            diagnosis_result["found_in_main_table"] = True
            diagnosis_result["main_table_records"] = [
                {
                    "id": record.id,
                    "platform": record.platform,
                    "conversion_id": record.conversion_id,
                    "click_id": record.click_id,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                    "conversion_status": getattr(record, 'conversion_status', None),
                    "is_deducted": getattr(record, 'is_deducted', False)
                }
                for record in main_records
            ]
            # 收集所有平台名称（使用集合推导式去重）
            platforms = list({r.platform for r in main_records})
            if len(platforms) > 1 or (len(platforms) == 1 and platforms[0] != "bft"):
                diagnosis_result["platform_name_changes"] = platforms
                diagnosis_result["suggestions"].append(
                    f"记录已找到，但平台名称可能已从 'bft' 变为 '{platforms[0]}'（根据广告主自动更新）。"
                    f"请在查询时选择平台为 '{platforms[0]}' 或使用'全部'。"
                )
        else:
            diagnosis_result["suggestions"].append(
                "在主表中未找到记录。可能原因：1) 数据验证失败 2) 被扣量 3) 重复检测跳过 4) 平台名称变化"
            )
        
        # 2. 检查扣减日志表（conversion_deduction_logs）
        deduction_query = select(ConversionDeductionLog).where(
            ConversionDeductionLog.click_id == conversion_or_click_id
        ).order_by(ConversionDeductionLog.created_at.desc())
        deduction_result = await db.execute(deduction_query)
        deduction_logs = deduction_result.scalars().all()
        
        if deduction_logs:
            diagnosis_result["found_in_deduction_logs"] = True
            diagnosis_result["deduction_logs"] = [
                {
                    "id": log.id,
                    "conversion_id": log.conversion_id,
                    "click_id": log.click_id,
                    "deducted_volume": log.deducted_volume,
                    "deducted_amount": float(log.deducted_amount) if log.deducted_amount else 0.0,
                    "original_amount": float(log.original_amount) if log.original_amount else 0.0,
                    "final_amount": float(log.final_amount) if log.final_amount else 0.0,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                    "deduction_reason": log.deduction_reason
                }
                for log in deduction_logs
            ]
            # 检查是否有被扣量的记录
            deducted_logs = [log for log in deduction_logs if log.deducted_volume > 0]
            if deducted_logs:
                diagnosis_result["suggestions"].append(
                    f"在扣减日志表中找到 {len(deducted_logs)} 条被扣量的记录。"
                    f"这些转化因扣量而未保存到主表，但会记录在扣减日志表中。"
                    f"可以在'扣减管理'页面查看这些记录。"
                )
        
        # 3. 检查通知记录表（postback_notifications）
        # 通过 click_id 或 conversion_id 查找通知记录
        notification_query = select(PostbackNotification).join(
            PostbackConversion,
            PostbackNotification.conversion_id == PostbackConversion.id
        ).where(
            or_(
                PostbackConversion.conversion_id == conversion_or_click_id,
                PostbackConversion.click_id == conversion_or_click_id
            )
        ).order_by(PostbackNotification.created_at.desc())
        notification_result = await db.execute(notification_query)
        notifications = notification_result.scalars().all()
        
        if notifications:
            diagnosis_result["found_in_notifications"] = True
            diagnosis_result["notifications"] = [
                {
                    "id": notif.id,
                    "conversion_id": notif.conversion_id,
                    "notification_type": notif.notification_type,
                    "notification_channel": notif.notification_channel,
                    "notification_status": notif.notification_status,
                    "created_at": notif.created_at.isoformat() if notif.created_at else None
                }
                for notif in notifications
            ]
            diagnosis_result["suggestions"].append(
                f"找到 {len(notifications)} 条通知记录，说明系统已收到并处理了该转化。"
            )
        
        # 4. 提供建议
        if not diagnosis_result["found_in_main_table"] and not diagnosis_result["found_in_deduction_logs"]:
            diagnosis_result["suggestions"].append(
                "未在任何表中找到记录。可能原因："
                "1) 数据验证失败，未保存到数据库"
                "2) 重复检测跳过（相同的转化已处理过）"
                "3) 点击ID或转化ID不正确"
                "建议：检查后端日志，搜索该 click_id 或 conversion_id"
            )
        elif not diagnosis_result["found_in_main_table"] and diagnosis_result["found_in_deduction_logs"]:
            diagnosis_result["suggestions"].append(
                "记录在扣减日志表中，但不在主表中。这是正常的，因为被扣量的转化不会保存到主表。"
                "可以在'扣减管理'页面查看这些记录。"
            )
        
        logger.info(
            f"管理员 {current_user.username} 诊断 PostBack 记录: "
            f"conversion_or_click_id={conversion_or_click_id}, "
            f"found_in_main={diagnosis_result['found_in_main_table']}, "
            f"found_in_deduction={diagnosis_result['found_in_deduction_logs']}, "
            f"found_in_notifications={diagnosis_result['found_in_notifications']}"
        )
        
        return ResponseBaseSchema.success(
            data=diagnosis_result,
            message="诊断完成"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"诊断 PostBack 记录失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"诊断失败: {str(e)}"
        )


# ====== 更新转化状态接口（融合转化日志功能） ======
@router.put("/postback/conversions/{conversion_id}/status",
            response_model=ResponseBaseSchema[dict],
            summary="更新转化状态（管理员）")
async def update_conversion_status(
    conversion_id: int = Path(..., ge=1, description="转化记录ID"),
    status: str = Query(..., description="转化状态（Approved/Pending）。注意：系统自动设置的状态（CapReached/OfferInactive/ClickExpired）不能手动设置"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    更新转化状态（仅管理员）
    融合转化日志功能
    
    注意：
    - 只能手动设置为 Approved 或 Pending
    - 系统自动设置的状态（CapReached/OfferInactive/ClickExpired）不能手动修改
    """
    try:
        result = await db.execute(
            select(PostbackConversion).where(PostbackConversion.id == conversion_id)
        )
        conversion = result.scalars().first()
        
        if not conversion:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"转化记录ID {conversion_id} 不存在"
            )
        
        # 验证状态值
        if status not in ['Approved', 'Pending']:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="转化状态必须是 'Approved' 或 'Pending'"
            )
        
        # 更新转化状态
        if hasattr(conversion, 'conversion_status'):
            conversion.conversion_status = status
            await db.commit()
            await db.refresh(conversion)
            
            logger.info(
                f"管理员 {current_user.username} 更新转化状态: "
                f"conversion_id={conversion_id}, status={status}"
            )
            
            return ResponseBaseSchema.success(
                data={"message": "状态更新成功", "conversion_id": conversion_id, "status": status}
            )
        else:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="PostbackConversion 模型缺少 conversion_status 字段"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新转化状态失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新失败：{str(e)}"
        )

