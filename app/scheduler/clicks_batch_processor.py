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
from app.core.utils import get_app_now_naive

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
                    # 1. 补充advertiser_id（如果缺失）
                    await _enrich_clicks_with_advertiser_id(db, clicks)
                    
                    # 2. 验证并清理short_link_id（如果不存在则设置为NULL）
                    await _validate_short_link_ids(db, clicks)
                    
                    # 3. 批量插入
                    inserted_count = await _batch_insert_clicks(db, clicks)
                    result['inserted'] += inserted_count
                    result['failed'] += len(clicks) - inserted_count
                    
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
                    result['failed'] += len(clicks)
        
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
                    if click_time.tzinfo is None:
                        click_time = click_time.replace(tzinfo=timezone.utc)
                except (ValueError, AttributeError):
                    click_time = now
            elif not isinstance(click_time, datetime):
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
                'created_at': now
            })
        
        # 批量插入（使用bulk insert提高性能）
        stmt = insert(Click).values(insert_data)
        await db.execute(stmt)
        
        logger.info(f"批量插入 {len(insert_data)} 条点击记录到数据库")
        return len(insert_data)
    except Exception as e:
        logger.error(f"批量插入点击记录失败: error={e}", exc_info=True)
        raise

