"""
重复检测器。

使用数据库唯一收据预留事件身份，覆盖不会写入 postback_conversions 的扣量事件。
普通转化在主记录写入后删除临时收据；扣量事件保留收据作为持久化幂等凭证。
"""
import logging
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PostbackConversion, PostbackEventReceipt
from app.core.postback_event_name import normalize_event_name

logger = logging.getLogger(__name__)


class DuplicateChecker:
    """重复检测器。"""

    @staticmethod
    async def is_duplicate(
        platform: str,
        conversion_id: Optional[str],
        event_name: Optional[str],
        db: AsyncSession,
    ) -> bool:
        """检查并原子预留事件身份；True 表示事件已处理或被其它事务预留。"""
        if not conversion_id:
            logger.debug("conversion_id 为空，跳过重复检测与收据预留")
            return False

        normalized_event = normalize_event_name(event_name)
        identity = (
            PostbackConversion.platform == platform,
            PostbackConversion.conversion_id == conversion_id,
            PostbackConversion.event_name == normalized_event,
        )

        # 兼容历史正式转化；其唯一约束仍是最终防线。
        result = await db.execute(
            select(PostbackConversion.id).where(*identity).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            logger.info(
                "检测到重复正式转化：platform=%s event_name=%s",
                platform,
                normalized_event,
            )
            return True

        receipt = PostbackEventReceipt(
            platform=platform,
            conversion_id=conversion_id,
            event_name=normalized_event,
        )
        try:
            # 唯一键冲突在 savepoint 内处理，不能让外层 Postback 事务进入 failed 状态。
            async with db.begin_nested():
                db.add(receipt)
                await db.flush()
        except IntegrityError:
            logger.info(
                "检测到重复或并发处理中事件收据：platform=%s event_name=%s",
                platform,
                normalized_event,
            )
            return True

        # 若本事务等待了另一个“普通转化”事务释放收据，正式转化此时已提交。
        # 二次查询封闭“临时收据删除后，第二个请求才成功插入”的竞态窗口。
        result = await db.execute(
            select(PostbackConversion.id)
            .where(*identity)
            .limit(1)
            .with_for_update()
        )
        if result.scalar_one_or_none() is not None:
            await db.delete(receipt)
            await db.flush()
            logger.info(
                "收据预留后发现正式转化已提交，跳过重复事件：platform=%s event_name=%s",
                platform,
                normalized_event,
            )
            return True

        return False

    @staticmethod
    async def release_receipt(
        platform: str,
        conversion_id: Optional[str],
        event_name: Optional[str],
        db: AsyncSession,
    ) -> None:
        """正式转化已在同一事务保存后，删除临时收据，依赖正式表唯一键长期防重。"""
        if not conversion_id:
            return
        normalized_event = normalize_event_name(event_name)
        await db.execute(
            delete(PostbackEventReceipt).where(
                PostbackEventReceipt.platform == platform,
                PostbackEventReceipt.conversion_id == conversion_id,
                PostbackEventReceipt.event_name == normalized_event,
            )
        )
