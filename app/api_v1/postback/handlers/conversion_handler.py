"""转化记录处理模块"""
import logging
from datetime import timedelta
from typing import Optional, Dict, Any

from fastapi import Request, HTTPException
from sqlalchemy import func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.constants import MAX_PAGE_SIZE
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.utils import parse_date_to_app_timezone, get_app_now_naive
from app.models.models import (
    OfferPublisherAssignment,
    PostbackConversion, Product, Client, PostbackNotification,
    Click, Offer, Publisher, Advertiser, User, ConversionDeductionLog
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.postback import PostbackConversionResponse

logger = logging.getLogger(__name__)


class ConversionHandler:
    """转化记录处理器"""

    async def get_postback_conversions(
            self,
            request: Request,
            platform: Optional[str],
            product_id: Optional[int],
            client_id: Optional[int],
            conversion_or_click_id: Optional[str],
            click_id: Optional[str],
            offer_id: Optional[int],
            publisher_id: Optional[int],
            advertiser_id: Optional[int],
            conversion_status: Optional[str],
            start_date: Optional[str],
            end_date: Optional[str],
            page: int,
            page_size: int,
            db: AsyncSession,
            current_user: User
    ):
        """
        查询 PostBack 转化记录（仅管理员）
        已融合转化日志功能，支持所有筛选条件
        """
        try:
            # 判断是否需要 JOIN Click 表（用于筛选 offer_id、publisher_id、advertiser_id）
            need_join_click = offer_id is not None or publisher_id is not None or advertiser_id is not None

            # 构建查询
            if need_join_click:
                query = select(PostbackConversion).join(Click, PostbackConversion.click_id == Click.click_id)
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
                conditions.append(Click.offer_id == offer_id)
            if publisher_id:
                conditions.append(Click.publisher_id == publisher_id)
            if advertiser_id:
                conditions.append(Click.advertiser_id == advertiser_id)
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
            if need_join_click:
                count_query = select(func.count(PostbackConversion.id)).select_from(
                    PostbackConversion.__table__.join(Click.__table__, PostbackConversion.click_id == Click.click_id)
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

            # 批量查询点击记录信息（通过 click_id 关联）
            # 使用集合去重，提高性能
            conversion_ids = list({conv.conversion_id for conv in conversions if conv.conversion_id})
            click_ids_from_conversions = list({conv.click_id for conv in conversions if conv.click_id})
            all_click_ids = list(set(conversion_ids + click_ids_from_conversions))
            clicks_map = {}
            offer_ids = set()
            publisher_ids = set()
            advertiser_ids = set()
            gid_publisher_ids = set()  # 通过 gid 关联的渠道ID

            # 查询 Click 表
            if all_click_ids:
                try:
                    clicks_query = select(
                        Click.click_id,
                        Click.offer_id,
                        Click.publisher_id,
                        Click.advertiser_id,
                        Click.click_time
                    ).where(Click.click_id.in_(all_click_ids))
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
                advertisers_query = select(Advertiser.id, Advertiser.advertiser_name).where(
                    Advertiser.id.in_(list(advertiser_ids))
                )
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

                # 通过 click_id 关联点击记录
                click_info = None
                if conv.click_id:
                    if conv.click_id in clicks_map:
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

    async def update_conversion_status(
            self,
            conversion_id: int,
            status: str,
            db: AsyncSession,
            current_user: User
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


conversion_handler = ConversionHandler()
