"""
点击记录 Redis 队列批量入库任务。

功能说明：
- 从 Redis clicks 队列批量 dequeue，批量 INSERT 到 clicks 表
- 高并发短链接场景下削峰填谷，避免同步写库拖慢重定向

在系统中的位置：
- 被 short_link_tasks 或独立 Cron 触发；队列见 ``app.core.clicks_queue``

注意事项：
1. IntegrityError 重复 click_id 应跳过单条继续批处理
2. 队列积压时增大 batch size 与执行频率，监控 queue length
"""
import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.clicks_queue import (
    acknowledge_reserved,
    drain_clicks_queue,
    get_queue_length,
    recover_processing_queue,
    requeue_reserved,
    reserve_clicks,
)
from app.core.tracking.click_persist import should_persist_clicks_to_db
from app.core.database import AsyncSessionLocal
from app.core.offer_cache import get_offer_advertiser_id, set_offer_cache
from app.core.utils import get_app_now_naive, APP_TIMEZONE
from app.models.models import Click, Offer, ShortLink

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
        'queue_remaining': 0,
        'skipped': False,
        'drained': 0,
    }

    if not should_persist_clicks_to_db():
        drained = await drain_clicks_queue()
        result['skipped'] = True
        result['drained'] = drained
        result['queue_remaining'] = await get_queue_length()
        if drained:
            logger.debug(
                "点击不落库模式：已丢弃队列积压 %s 条，剩余 %s",
                drained,
                result['queue_remaining'],
            )
        return result

    try:
        recovered = await recover_processing_queue()
        if recovered:
            logger.info("点击队列启动恢复：processing → 主队列 %s 条", recovered)

        # 循环处理，直到队列为空或达到最大批次数（防止长时间占用）
        max_batches = 10  # 最多处理10批（10,000条记录）
        batch_count = 0
        processing_started_at = time.monotonic()

        while (
            batch_count < max_batches
            and time.monotonic() - processing_started_at < MAX_BATCH_TIME
        ):
            # 获取队列长度
            queue_length = await get_queue_length()
            if queue_length == 0:
                if batch_count == 0:
                    logger.debug("点击队列为空，无需处理")
                else:
                    logger.debug(f"点击队列已处理完毕，共处理 {batch_count} 批")
                break

            logger.debug(f"开始批量处理点击记录队列（第 {batch_count + 1} 批），队列长度: {queue_length}")

            # 原子预留：主队列 → processing（失败时可回队）
            reserved = await reserve_clicks(count=min(BATCH_SIZE, queue_length))
            if not reserved:
                break

            raw_items = [raw for raw, _ in reserved]
            clicks = [data for _, data in reserved]

            batch_count += 1
            result['processed'] += len(clicks)
            batch_failed = False
            valid_clicks: List[Dict[str, Any]] = []

            # 批量插入到数据库
            async with AsyncSessionLocal() as db:
                try:
                    # 1. 验证并过滤offer_id（如果不存在则移除该记录）
                    valid_clicks = await _validate_offer_ids(db, clicks)
                    if not valid_clicks:
                        logger.warning(f"第 {batch_count} 批：所有点击记录的offer_id都无效，跳过插入")
                        result['failed'] += len(clicks)
                        await acknowledge_reserved(raw_items)
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

                    # 4. 批量插入 Click 记录
                    inserted_count, duplicate_count = await _batch_insert_clicks(db, valid_clicks)
                    result['inserted'] += inserted_count
                    result['deduplicated'] = result.get('deduplicated', 0) + duplicate_count
                    result['failed'] += len(valid_clicks) - inserted_count - duplicate_count

                    await db.commit()
                    await acknowledge_reserved(raw_items)
                    logger.debug(
                        f"批量插入点击记录成功（第 {batch_count} 批）: "
                        f"处理={len(clicks)}, "
                        f"插入={inserted_count}, "
                        f"重复跳过={duplicate_count}, "
                        f"失败={len(clicks) - inserted_count - duplicate_count}"
                    )
                except Exception as e:
                    await db.rollback()
                    batch_failed = True
                    logger.error(
                        f"批量插入点击记录失败（第 {batch_count} 批）: error={e}",
                        exc_info=True
                    )
                    result['failed'] += len(valid_clicks) if 'valid_clicks' in locals() else len(clicks)
                    await requeue_reserved(raw_items)

            if batch_failed:
                # 本批已回队，避免同轮循环反复处理
                break

        # 获取剩余队列长度
        result['queue_remaining'] = await get_queue_length()

        # 注意：处理结果日志由调用方（short_link_tasks.py）统一输出，避免重复

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
            logger.error("批量查询 Offer 失败，保留原始队列记录并重试: %s", e, exc_info=True)
            raise

    # 补充advertiser_id到点击记录
    for click in clicks:
        offer_id = click.get('offer_id')
        if offer_id and offer_id in offer_advertiser_map:
            if not click.get('advertiser_id'):
                click['advertiser_id'] = offer_advertiser_map[offer_id]


async def _validate_offer_ids(db: AsyncSession, clicks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    验证并清理offer_id（如果不存在则设置为None）
    支持两种格式的offer_id：
    1. 数据库主键ID（Offer.id）
    2. 上游Offer ID（Offer.advertiser_offer_id）- 会自动转换为数据库主键ID
    
    防止外键约束失败，但允许保存记录（因为数据库允许offer_id为NULL）
    
    Args:
        db: 数据库会话
        clicks: 点击记录列表
        
    Returns:
        有效的点击记录列表（无效的offer_id已被设置为None，上游Offer ID已转换为主键ID）
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
        # 1. 先尝试作为主键ID查询（Offer.id）
        result = await db.execute(
            select(Offer.id)
            .where(Offer.id.in_(offer_ids_to_validate))
        )
        valid_offer_ids = {row[0] for row in result.all()}

        # 2. 对于未找到的offer_id，尝试作为上游Offer ID查询（Offer.advertiser_offer_id）
        # 注意：advertiser_offer_id 是字符串类型，需要转换
        unmatched_offer_ids = offer_ids_to_validate - valid_offer_ids
        upstream_offer_id_map = {}  # 上游Offer ID -> 数据库主键ID的映射

        if unmatched_offer_ids:
            # 将数字转换为字符串，因为advertiser_offer_id是String类型
            upstream_offer_id_strs = [str(oid) for oid in unmatched_offer_ids]
            result = await db.execute(
                select(Offer.id, Offer.advertiser_offer_id)
                .where(Offer.advertiser_offer_id.in_(upstream_offer_id_strs))
            )
            for row in result.all():
                db_offer_id, upstream_offer_id = row
                # 将字符串转换回数字，用于匹配
                try:
                    upstream_id_int = int(upstream_offer_id)
                    upstream_offer_id_map[upstream_id_int] = db_offer_id
                except (ValueError, TypeError):
                    # 如果转换失败，跳过
                    pass

        # 3. 更新点击记录中的offer_id
        # 如果offer_id是上游Offer ID，转换为数据库主键ID
        cleaned_count = 0
        converted_count = 0
        invalid_offer_ids = set()

        for click in clicks:
            offer_id = click.get('offer_id')
            if offer_id is None:
                continue

            # 如果已经是有效的主键ID，保持不变
            if offer_id in valid_offer_ids:
                continue

            # 如果是上游Offer ID，转换为数据库主键ID
            if offer_id in upstream_offer_id_map:
                db_offer_id = upstream_offer_id_map[offer_id]
                click['offer_id'] = db_offer_id
                converted_count += 1
                logger.debug(
                    f"将上游Offer ID {offer_id} 转换为数据库主键ID {db_offer_id}。"
                    f"click_id={click.get('click_id')}, short_link_id={click.get('short_link_id')}"
                )
            else:
                # 既不是主键ID，也不是上游Offer ID，设置为None
                logger.warning(
                    f"Offer ID {offer_id} 不存在（既不是主键ID，也不是上游Offer ID），将设置为None（允许保存记录）。"
                    f"click_id={click.get('click_id')}, short_link_id={click.get('short_link_id')}"
                )
                click['offer_id'] = None
                cleaned_count += 1
                invalid_offer_ids.add(offer_id)

        if cleaned_count > 0 or converted_count > 0:
            logger.info(
                f"验证offer_id完成: 有效主键ID数={len(valid_offer_ids)}, "
                f"已转换上游Offer ID数={converted_count}, "
                f"无效offer_id数={len(invalid_offer_ids)}, "
                f"已清理记录数={cleaned_count}（设置为None）。所有记录将被保存。"
            )

        # 返回所有记录（无效的offer_id已被设置为None，上游Offer ID已转换为主键ID）
        return clicks
    except Exception as e:
        # DB 查询失败时真实有效性未知；不能把关联 ID 清空后继续入库，否则会永久丢失归因。
        logger.error("验证 Offer ID 失败，保留原始记录并回队重试: %s", e, exc_info=True)
        raise


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
        # DB 查询失败不等于短链不存在；清空 FK 会造成无法恢复的归因数据丢失。
        logger.error("验证 short_link_id 失败，保留原始记录并回队重试: %s", e, exc_info=True)
        raise


async def _batch_insert_clicks(
    db: AsyncSession,
    clicks: List[Dict[str, Any]],
) -> tuple[int, int]:
    """
    批量插入点击记录。

    返回 (新插入数, 已存在/并发重复数)。批量 INSERT 遇到唯一键冲突后先回滚失败
    事务，再通过 SAVEPOINT 逐条插入；非重复完整性错误继续抛出，交由队列回队重试。
    """
    if not clicks:
        return 0, 0

    try:
        insert_data = []
        now = get_app_now_naive()

        for click in clicks:
            click_time = click.get("click_time")
            if isinstance(click_time, str):
                try:
                    if click_time.endswith("Z"):
                        click_time = click_time[:-1] + "+00:00"
                    click_time = datetime.fromisoformat(click_time)
                    if click_time.tzinfo is not None:
                        click_time = click_time.astimezone(timezone.utc)
                        click_time = click_time.astimezone(APP_TIMEZONE).replace(tzinfo=None)
                except (ValueError, AttributeError):
                    click_time = now
            elif isinstance(click_time, datetime):
                if click_time.tzinfo is not None:
                    click_time = click_time.astimezone(timezone.utc)
                    click_time = click_time.astimezone(APP_TIMEZONE).replace(tzinfo=None)
            else:
                click_time = now

            insert_data.append({
                "click_id": click.get("click_id"),
                "offer_id": click.get("offer_id"),
                "publisher_id": click.get("publisher_id"),
                "advertiser_id": click.get("advertiser_id"),
                "short_link_id": click.get("short_link_id"),
                "click_time": click_time,
                "ip": click.get("ip"),
                "device": click.get("device"),
                "country": click.get("country"),
                "user_agent": click.get("user_agent"),
                "referer": click.get("referer"),
                "conversion_id": click.get("conversion_id"),
                "created_at": now,
                "os": click.get("os"),
                "os_version": click.get("os_version"),
                "browser": click.get("browser"),
                "browser_version": click.get("browser_version"),
                "accept_language": click.get("accept_language"),
                "accept_encoding": click.get("accept_encoding"),
                "is_bot": click.get("is_bot", False),
                "device_type": click.get("device_type"),
                "device_brand": click.get("device_brand"),
                "device_model": click.get("device_model"),
                "url_params": click.get("url_params"),
                "all_headers": click.get("all_headers"),
                "original_request_url": click.get("original_request_url"),
                "final_redirect_url": click.get("final_redirect_url"),
            })

        click_ids = [item["click_id"] for item in insert_data if item.get("click_id")]
        duplicate_count = 0
        if click_ids:
            result = await db.execute(
                select(Click.click_id).where(Click.click_id.in_(click_ids))
            )
            existing_click_ids = {row[0] for row in result.all()}
            if existing_click_ids:
                duplicate_count += sum(
                    1 for item in insert_data
                    if item.get("click_id") in existing_click_ids
                )
                insert_data = [
                    item for item in insert_data
                    if item.get("click_id") not in existing_click_ids
                ]

        if not insert_data:
            logger.debug("点击记录均已存在，作为幂等重复跳过")
            return 0, duplicate_count

        try:
            await db.execute(insert(Click).values(insert_data))
            return len(insert_data), duplicate_count
        except IntegrityError as bulk_error:
            error_msg = str(bulk_error.orig if getattr(bulk_error, "orig", None) else bulk_error)
            lowered = error_msg.lower()
            is_duplicate = (
                "duplicate entry" in lowered
                or "unique constraint" in lowered
                or "unique violation" in lowered
            )
            if not is_duplicate:
                raise

            # 批量事务已进入失败状态；先回滚，再用 SAVEPOINT 隔离每条记录。
            await db.rollback()
            inserted_count = 0
            for item in insert_data:
                try:
                    async with db.begin_nested():
                        await db.execute(insert(Click).values([item]))
                    inserted_count += 1
                except IntegrityError as row_error:
                    row_msg = str(
                        row_error.orig if getattr(row_error, "orig", None) else row_error
                    ).lower()
                    row_duplicate = (
                        "duplicate entry" in row_msg
                        or "unique constraint" in row_msg
                        or "unique violation" in row_msg
                    )
                    if row_duplicate:
                        duplicate_count += 1
                        continue
                    raise
            logger.info(
                "点击记录批量插入遇到并发重复，已逐条隔离处理: inserted=%s duplicate=%s",
                inserted_count, duplicate_count,
            )
            return inserted_count, duplicate_count

    except Exception as e:
        logger.error("批量插入点击记录失败: error=%s", e, exc_info=True)
        raise

        logger.error(f"批量插入点击记录失败: error={e}", exc_info=True)
        raise
