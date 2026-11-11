"""
Cap计数一致性校验工具
用于校验DB和Redis中的Cap计数是否一致
"""
import logging
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import OfferCap
from app.core.cap.redis_counter import get_daily_cap_key, get_total_cap_key
from app.core.redis_client import get_redis_client
from app.core.utils import get_app_now_naive

logger = logging.getLogger(__name__)


async def check_cap_consistency(
    db: AsyncSession,
    offer_id: int = None,
    fix_inconsistencies: bool = False
) -> List[Dict[str, Any]]:
    """检查 DB/Redis Cap 计数；Redis key 缺失时将状态标记为未知，绝不推断为 0。"""
    inconsistencies = []

    try:
        query = select(OfferCap).where(OfferCap.is_active == True)
        if offer_id:
            query = query.where(OfferCap.offer_id == offer_id)

        result = await db.execute(query)
        caps = result.scalars().all()

        redis = await get_redis_client()
        if not redis:
            # 无法读取 Redis 时，不能把“未知”伪装成“无不一致”。
            # 通过异常让 API 返回失败状态，调用方可明确区分检查失败与检查通过。
            logger.error("Redis不可用，Cap一致性检查无法完成")
            raise RuntimeError("Redis 不可用，无法完成 Cap 计数一致性检查")

        now = get_app_now_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        for cap in caps:
            cap_issues = []
            redis_daily_count = None
            redis_total_count = None
            db_daily_count = None
            db_total_count = None

            if cap.daily_cap:
                if cap.cap_start_date and cap.cap_start_date.date() == today_start.date():
                    db_daily_count = cap.current_daily_count
                else:
                    db_daily_count = 0

                redis_key = get_daily_cap_key(cap.offer_id, now, cap.publisher_id)
                redis_val = await redis.get(redis_key)
                if redis_val is None:
                    cap_issues.append(
                        "每日 Redis 计数 key 缺失，真实计数未知；不按 0 处理，也不执行自动修复"
                    )
                else:
                    redis_daily_count = int(redis_val)
                    if redis_daily_count != db_daily_count:
                        cap_issues.append(
                            f"每日计数不一致: DB={db_daily_count}, Redis={redis_daily_count}"
                        )
                        if fix_inconsistencies:
                            logger.warning(
                                "Cap 自动修复已禁用（每日计数）；需通过持行锁的安全同步流程处理：cap_id=%s",
                                cap.id,
                            )

            if cap.total_cap:
                db_total_count = cap.current_total_count
                redis_key = get_total_cap_key(cap.offer_id, cap.publisher_id)
                redis_val = await redis.get(redis_key)
                if redis_val is None:
                    cap_issues.append(
                        "总计 Redis 计数 key 缺失，真实计数未知；不按 0 处理，也不执行自动修复"
                    )
                else:
                    redis_total_count = int(redis_val)
                    if redis_total_count != db_total_count:
                        cap_issues.append(
                            f"总计数不一致: DB={db_total_count}, Redis={redis_total_count}"
                        )
                        if fix_inconsistencies:
                            logger.warning(
                                "Cap 自动修复已禁用（总计数）；需通过持行锁的安全同步流程处理：cap_id=%s",
                                cap.id,
                            )

            if cap_issues:
                if fix_inconsistencies:
                    cap_issues.append(
                        "未执行自动覆盖修复：为保护并发预留，需使用安全同步/人工核验流程"
                    )
                inconsistencies.append({
                    "cap_id": cap.id,
                    "offer_id": cap.offer_id,
                    "publisher_id": cap.publisher_id,
                    "db_daily_count": db_daily_count,
                    "redis_daily_count": redis_daily_count,
                    "db_total_count": db_total_count,
                    "redis_total_count": redis_total_count,
                    "inconsistencies": cap_issues,
                })

        if inconsistencies:
            logger.warning("发现 %s 个Cap计数问题", len(inconsistencies))
        else:
            logger.info("Cap计数一致性检查通过")

        return inconsistencies

    except Exception as e:
        logger.error("Cap计数一致性检查失败: %s", str(e), exc_info=True)
        raise
