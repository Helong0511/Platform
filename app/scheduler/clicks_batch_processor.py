"""
点击记录批量处理任务（高并发优化）
从Redis队列批量取出点击记录，批量插入到数据库
"""
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert
from app.core.database import AsyncSessionLocal
from app.core.clicks_queue import dequeue_clicks, get_queue_length
from app.core.offer_cache import get_offer_advertiser_id, set_offer_cache
from app.models.models import Click, Offer, ShortLink
from sqlalchemy.future import select
from app.core.utils import get_app_now_naive, APP_TIMEZONE

logger = logging.getLogger(__name__)

# 批量处理大小
BATCH_SIZE = 1000
# 最大批处理时间（秒）
MAX_BATCH_TIME = 30


async def process_clicks_queue() -> Dict[str, int]:
    """
    批量处理点击记录队列（循环处理直到队列为空或达到最大批次数）
    
    Returns:
        处理结果统计：{
            'processed': 处理的记录数,
            'inserted': 成功插入的记录数,
            'failed': 失败的记录数,
            'queue_remaining': 队列剩余记录数
        }
    """
    result = {
        'processed': 0,
        'inserted': 0,
        'failed': 0,
        'queue_remaining': 0
    }
    
    try:
        # 循环处理，直到队列为空或达到最大批次数（防止长时间占用）
        max_batches = 10  # 最多处理10批（10,000条记录）
        batch_count = 0
        
        while batch_count < max_batches:
            # 获取队列长度
            queue_length = await get_queue_length()
            if queue_length == 0:
                if batch_count == 0:
                    logger.debug("点击队列为空，无需处理")
                else:
                    logger.info(f"点击队列已处理完毕，共处理 {batch_count} 批")
                break
            
            logger.info(f"开始批量处理点击记录队列（第 {batch_count + 1} 批），队列长度: {queue_length}")
            
            # 批量从队列取出点击记录
            clicks = await dequeue_clicks(count=min(BATCH_SIZE, queue_length))
            if not clicks:
                break
            
            batch_count += 1
            result['processed'] += len(clicks)
            
            # 批量插入到数据库
            async with AsyncSessionLocal() as db:
                try:
                    # 1. 验证并过滤offer_id（如果不存在则移除该记录）
                    valid_clicks = await _validate_offer_ids(db, clicks)
                    if not valid_clicks:
                        logger.warning(f"第 {batch_count} 批：所有点击记录的offer_id都无效，跳过插入")
                        result['failed'] += len(clicks)
                        continue
                    
                    # 记录被过滤的记录数
                    filtered_count = len(clicks) - len(valid_clicks)
                    if filtered_count > 0:
                        result['failed'] += filtered_count
                        logger.warning(
                            f"第 {batch_count} 批：过滤了 {filtered_count} 条无效记录，"
                            f"剩余 {len(valid_clicks)} 条有效记录"
                        )
                    
                    # 2. 补充advertiser_id（如果缺失）
                    await _enrich_clicks_with_advertiser_id(db, valid_clicks)
                    
                    # 3. 验证并清理short_link_id（如果不存在则设置为NULL）
                    await _validate_short_link_ids(db, valid_clicks)
                    
                    # 4. 批量插入
                    inserted_count = await _batch_insert_clicks(db, valid_clicks)
                    result['inserted'] += inserted_count
                    result['failed'] += len(valid_clicks) - inserted_count
                    
                    await db.commit()
                    logger.info(
                        f"批量插入点击记录成功（第 {batch_count} 批）: "
                        f"处理={len(clicks)}, "
                        f"插入={inserted_count}, "
                        f"失败={len(clicks) - inserted_count}"
                    )
                except Exception as e:
                    await db.rollback()
                    logger.error(
                        f"批量插入点击记录失败（第 {batch_count} 批）: error={e}",
                        exc_info=True
                    )
                    # 使用 valid_clicks 的长度（如果存在），否则使用 clicks
                    result['failed'] += len(valid_clicks) if 'valid_clicks' in locals() else len(clicks)
        
        # 获取剩余队列长度
        result['queue_remaining'] = await get_queue_length()
        
        if result['processed'] > 0:
            logger.info(
                f"点击队列批量处理完成: "
                f"总处理={result['processed']}, "
                f"总插入={result['inserted']}, "
                f"总失败={result['failed']}, "
                f"队列剩余={result['queue_remaining']}"
            )
        
    except Exception as e:
        logger.error(f"处理点击队列异常: error={e}", exc_info=True)
    
    return result


async def _enrich_clicks_with_advertiser_id(db: AsyncSession, clicks: List[Dict[str, Any]]) -> None:
    """
    为点击记录补充advertiser_id（如果缺失）
    优先使用缓存，减少数据库查询
    
    Args:
        db: 数据库会话
        clicks: 点击记录列表
    """
    # 收集需要查询的offer_id
    offer_ids_to_query = set()
    for click in clicks:
        if click.get('offer_id') and not click.get('advertiser_id'):
            offer_ids_to_query.add(click['offer_id'])
    
    if not offer_ids_to_query:
        return
    
    # 从缓存获取advertiser_id
    offer_advertiser_map = {}
    for offer_id in offer_ids_to_query:
        cached_advertiser_id = await get_offer_advertiser_id(offer_id)
        if cached_advertiser_id:
            offer_advertiser_map[offer_id] = cached_advertiser_id
    
    # 查询缓存中没有的Offer
    offer_ids_to_db = offer_ids_to_query - set(offer_advertiser_map.keys())
    if offer_ids_to_db:
        try:
            result = await db.execute(
                select(Offer.id, Offer.advertiser_id, Offer.offer_name)
                .where(Offer.id.in_(offer_ids_to_db))
            )
            for row in result.all():
                offer_id, advertiser_id, offer_name = row
                offer_advertiser_map[offer_id] = advertiser_id
                # 缓存Offer信息
                await set_offer_cache(offer_id, advertiser_id, offer_name)
        except Exception as e:
            logger.warning(f"批量查询Offer失败: error={e}")
    
    # 补充advertiser_id到点击记录
    for click in clicks:
        offer_id = click.get('offer_id')
        if offer_id and offer_id in offer_advertiser_map:
            if not click.get('advertiser_id'):
                click['advertiser_id'] = offer_advertiser_map[offer_id]


async def _validate_offer_ids(db: AsyncSession, clicks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    验证并清理offer_id（如果不存在则设置为None）
    防止外键约束失败，但允许保存记录（因为数据库允许offer_id为NULL）
    
    Args:
        db: 数据库会话
        clicks: 点击记录列表
        
    Returns:
        有效的点击记录列表（无效的offer_id已被设置为None）
    """
    # 收集所有需要验证的offer_id（不为None的）
    offer_ids_to_validate = set()
    for click in clicks:
        offer_id = click.get('offer_id')
        if offer_id is not None:
            offer_ids_to_validate.add(offer_id)
    
    # 如果没有需要验证的offer_id，直接返回所有记录（允许offer_id为None）
    if not offer_ids_to_validate:
        logger.debug(f"所有点击记录的offer_id都为None，允许保存（数据库允许NULL）")
        return clicks
    
    try:
        # 批量查询存在的offer_id
        result = await db.execute(
            select(Offer.id)
            .where(Offer.id.in_(offer_ids_to_validate))
        )
        valid_offer_ids = {row[0] for row in result.all()}
        
        # 验证并清理无效的offer_id（设置为None而不是跳过记录）
        cleaned_count = 0
        for click in clicks:
            offer_id = click.get('offer_id')
            if offer_id is not None and offer_id not in valid_offer_ids:
                logger.warning(
                    f"Offer ID {offer_id} 不存在，将设置为None（允许保存记录）。"
                    f"click_id={click.get('click_id')}, short_link_id={click.get('short_link_id')}"
                )
                click['offer_id'] = None
                cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(
                f"验证offer_id完成: 有效={len(offer_ids_to_validate) - cleaned_count}, "
                f"已清理={cleaned_count}（设置为None）。所有记录将被保存。"
            )
        
        # 返回所有记录（无效的offer_id已被设置为None）
        return clicks
    except Exception as e:
        logger.error(f"验证offer_id失败: error={e}，将清空所有offer_id以避免外键约束错误", exc_info=True)
        # 如果验证失败，清空所有offer_id以避免外键约束错误，但仍保存记录
        for click in clicks:
            if click.get('offer_id') is not None:
                click['offer_id'] = None
        return clicks


async def _validate_short_link_ids(db: AsyncSession, clicks: List[Dict[str, Any]]) -> None:
    """
    验证并清理short_link_id（如果不存在则设置为NULL）
    防止外键约束失败
    
    Args:
        db: 数据库会话
        clicks: 点击记录列表
    """
    # 收集所有需要验证的short_link_id
    short_link_ids_to_validate = set()
    for click in clicks:
        short_link_id = click.get('short_link_id')
        if short_link_id is not None:
            short_link_ids_to_validate.add(short_link_id)
    
    if not short_link_ids_to_validate:
        return
    
    try:
        # 批量查询存在的short_link_id
        result = await db.execute(
            select(ShortLink.id)
            .where(ShortLink.id.in_(short_link_ids_to_validate))
        )
        valid_short_link_ids = {row[0] for row in result.all()}
        
        # 将不存在的short_link_id设置为NULL
        for click in clicks:
            short_link_id = click.get('short_link_id')
            if short_link_id is not None and short_link_id not in valid_short_link_ids:
                logger.warning(
                    f"短链接ID {short_link_id} 不存在，将设置为NULL。"
                    f"click_id={click.get('click_id')}, offer_id={click.get('offer_id')}"
                )
                click['short_link_id'] = None
    except Exception as e:
        logger.warning(f"验证short_link_id失败: error={e}，将清空所有short_link_id")
        # 如果验证失败，清空所有short_link_id以避免外键约束错误
        for click in clicks:
            if click.get('short_link_id') is not None:
                click['short_link_id'] = None


async def _batch_insert_clicks(db: AsyncSession, clicks: List[Dict[str, Any]]) -> int:
    """
    批量插入点击记录到数据库（高并发优化）
    
    Args:
        db: 数据库会话
        clicks: 点击记录列表
        
    Returns:
        成功插入的记录数
    """
    if not clicks:
        return 0
    
    try:
        # 准备批量插入数据
        insert_data = []
        now = get_app_now_naive()  # 使用北京时间
        
        for click in clicks:
            # 处理click_time（可能是ISO格式字符串或datetime对象）
            click_time = click.get('click_time')
            if isinstance(click_time, str):
                try:
                    # 解析ISO格式字符串
                    if click_time.endswith('Z'):
                        click_time = click_time[:-1] + '+00:00'
                    click_time = datetime.fromisoformat(click_time)
                    # 如果带时区信息，转换为北京时间（naive）
                    if click_time.tzinfo is not None:
                        # 转换为UTC时间，再转换为北京时间
                        if click_time.tzinfo != timezone.utc:
                            # 先转换为UTC
                            click_time = click_time.astimezone(timezone.utc)
                        # 从UTC转换为北京时间（naive）
                        click_time = click_time.replace(tzinfo=timezone.utc).astimezone(APP_TIMEZONE).replace(tzinfo=None)
                    # 如果已经是naive，假设是北京时间（新数据都是北京时间）
                except (ValueError, AttributeError):
                    click_time = now
            elif isinstance(click_time, datetime):
                # 如果是datetime对象
                if click_time.tzinfo is not None:
                    # 带时区信息，转换为北京时间（naive）
                    if click_time.tzinfo != timezone.utc:
                        # 先转换为UTC
                        click_time = click_time.astimezone(timezone.utc)
                    # 从UTC转换为北京时间（naive）
                    click_time = click_time.replace(tzinfo=timezone.utc).astimezone(APP_TIMEZONE).replace(tzinfo=None)
                # 如果已经是naive，假设是北京时间（新数据都是北京时间）
            else:
                click_time = now
            
            insert_data.append({
                'click_id': click.get('click_id'),
                'offer_id': click.get('offer_id'),
                'publisher_id': click.get('publisher_id'),
                'advertiser_id': click.get('advertiser_id'),
                'short_link_id': click.get('short_link_id'),
                'click_time': click_time,
                'ip': click.get('ip'),
                'device': click.get('device'),
                'country': click.get('country'),
                'user_agent': click.get('user_agent'),
                'referer': click.get('referer'),
                'conversion_id': click.get('conversion_id'),
                'created_at': now,
                # 软件信息
                'os': click.get('os'),
                'os_version': click.get('os_version'),
                'browser': click.get('browser'),
                'browser_version': click.get('browser_version'),
                'accept_language': click.get('accept_language'),
                'accept_encoding': click.get('accept_encoding'),
                'is_bot': click.get('is_bot', False),
                # 硬件信息
                'device_type': click.get('device_type'),
                'device_brand': click.get('device_brand'),
                'device_model': click.get('device_model'),
                # URL参数和请求头
                'url_params': click.get('url_params'),
                'all_headers': click.get('all_headers'),
            })
        
        # 批量插入（使用bulk insert提高性能）
        stmt = insert(Click).values(insert_data)
        await db.execute(stmt)
        
        logger.info(f"批量插入 {len(insert_data)} 条点击记录到数据库")
        return len(insert_data)
    except Exception as e:
        logger.error(f"批量插入点击记录失败: error={e}", exc_info=True)
        raise

