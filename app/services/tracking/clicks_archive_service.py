"""
点击记录归档服务（主表 clicks → clicks_archive）。

职责：
- 将 click_time 早于保留期的记录完整写入归档表，核对数量后再删除主表
- 归档表不存在时自动 CREATE；令牌模式且主表为空时跳过

默认保留 90 天；由定时任务 archive_old_clicks 调用模块单例 clicks_archive_service。
"""
import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_errors import get_mysql_errno
from app.core.tracking.click_persist import should_persist_clicks_to_db
from app.core.utils import get_app_now_naive

logger = logging.getLogger(__name__)

_CREATE_ARCHIVE_TABLE_SQL = """
CREATE TABLE `clicks_archive`
(
    `id` int NOT NULL AUTO_INCREMENT COMMENT '点击记录ID',
    `click_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    `offer_id` int NULL DEFAULT NULL,
    `publisher_id` int NULL DEFAULT NULL,
    `advertiser_id` int NULL DEFAULT NULL,
    `short_link_id` int NULL DEFAULT NULL,
    `click_time` datetime NOT NULL,
    `ip` varchar(50) NULL DEFAULT NULL,
    `device` varchar(100) NULL DEFAULT NULL,
    `country` varchar(50) NULL DEFAULT NULL,
    `user_agent` text NULL,
    `referer` text NULL,
    `conversion_id` int NULL DEFAULT NULL,
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `os` varchar(50) NULL DEFAULT NULL,
    `os_version` varchar(50) NULL DEFAULT NULL,
    `browser` varchar(50) NULL DEFAULT NULL,
    `browser_version` varchar(50) NULL DEFAULT NULL,
    `accept_language` varchar(200) NULL DEFAULT NULL,
    `accept_encoding` varchar(200) NULL DEFAULT NULL,
    `is_bot` tinyint(1) NOT NULL DEFAULT 0,
    `device_type` varchar(20) NULL DEFAULT NULL,
    `device_brand` varchar(50) NULL DEFAULT NULL,
    `device_model` varchar(100) NULL DEFAULT NULL,
    `url_params` text NULL,
    `all_headers` text NULL,
    `original_request_url` text NULL,
    `final_redirect_url` text NULL,
    PRIMARY KEY (`id`) USING BTREE,
    INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
    INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
    INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
    INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
    INDEX `idx_short_link_id`(`short_link_id` ASC) USING BTREE,
    INDEX `idx_click_time`(`click_time` ASC) USING BTREE,
    INDEX `idx_conversion_id`(`conversion_id` ASC) USING BTREE,
    INDEX `idx_clicks_time_offer_publisher`(`click_time` ASC, `offer_id` ASC, `publisher_id` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '点击记录归档表';
"""


class ClicksArchiveService:
    """
    点击数据冷热分离服务。

    使用普通 INSERT ... SELECT；任何重复键或写入异常都会回滚，
    只有归档与删除数量均核对一致后才提交；模块级单例供定时任务调用。
    """

    async def count_clicks(self, db: AsyncSession) -> int:
        """统计主表 clicks 当前总行数。"""
        result = await db.execute(text("SELECT COUNT(*) FROM `clicks`"))
        return int(result.scalar() or 0)

    async def should_skip_archive(self, db: AsyncSession) -> bool:
        """
        判断是否应跳过归档。

        当 should_persist_clicks_to_db() 为 False（令牌模式）且主表为空时返回 True，
        表示新流量不再写入 clicks，无需执行归档迁移。
        """
        if should_persist_clicks_to_db():
            return False
        return await self.count_clicks(db) == 0

    async def archive_old_clicks(
        self,
        db: AsyncSession,
        days: int = 90,
        batch_size: int = 1000,
    ) -> Dict[str, Any]:
        """
        按有界批次归档过期点击记录；每批独立事务，失败后可从主表剩余记录续跑。

        先固定本轮主表最大 ID，避免归档期间持续写入的延迟点击让本轮任务无限延长。
        每批通过 SELECT ... FOR UPDATE 锁定明确的源记录，再按 ID 写入归档表、
        核对插入/删除数量并提交；任一批次失败只回滚当前批次，已提交批次保持完整。
        """
        if type(days) is not int or days < 1:
            raise ValueError("days 必须是大于等于 1 的整数")
        if type(batch_size) is not int or not 1 <= batch_size <= 10_000:
            raise ValueError("batch_size 必须是 1 到 10000 之间的整数")

        now = get_app_now_naive()
        archive_date = now - timedelta(days=days)
        archive_date_str = archive_date.strftime("%Y-%m-%d %H:%M:%S")

        if await self.should_skip_archive(db):
            await db.rollback()
            logger.info("点击不落库模式且主表为空，跳过归档任务")
            return {
                "archived_count": 0,
                "deleted_count": 0,
                "batch_count": 0,
                "high_water_id": None,
                "archive_date": archive_date_str,
                "skipped": True,
                "message": "点击不落库模式，主表无数据，已跳过归档",
            }

        await self._ensure_archive_table(db)

        # 固定本轮扫描上界；任务执行期间新产生的点击留给下一轮，避免无界追赶。
        max_id_result = await db.execute(text("SELECT MAX(`id`) FROM `clicks`"))
        high_water_id = max_id_result.scalar()
        if high_water_id is None:
            await db.rollback()
            return {
                "archived_count": 0,
                "deleted_count": 0,
                "batch_count": 0,
                "high_water_id": None,
                "archive_date": archive_date_str,
                "skipped": False,
                "message": "没有需要归档的数据",
            }
        high_water_id = int(high_water_id)

        select_ids_stmt = text(
            """
            SELECT `id`
            FROM `clicks`
            WHERE `click_time` < :archive_date
              AND `id` <= :high_water_id
            ORDER BY `click_time` ASC, `id` ASC
            LIMIT :batch_size
            FOR UPDATE
            """
        )

        # SQLAlchemy expanding bind 将 ID 列表安全展开为 IN (...), 不拼接用户输入 SQL。
        insert_stmt = text(
            """
            INSERT INTO `clicks_archive`
            (`id`, `click_id`, `offer_id`, `publisher_id`, `advertiser_id`,
             `short_link_id`, `click_time`, `ip`, `device`, `country`,
             `user_agent`, `referer`, `conversion_id`, `created_at`,
             `os`, `os_version`, `browser`, `browser_version`,
             `accept_language`, `accept_encoding`, `is_bot`,
             `device_type`, `device_brand`, `device_model`,
             `url_params`, `all_headers`, `original_request_url`,
             `final_redirect_url`)
            SELECT `id`, `click_id`, `offer_id`, `publisher_id`, `advertiser_id`,
                   `short_link_id`, `click_time`, `ip`, `device`, `country`,
                   `user_agent`, `referer`, `conversion_id`, `created_at`,
                   `os`, `os_version`, `browser`, `browser_version`,
                   `accept_language`, `accept_encoding`, `is_bot`,
                   `device_type`, `device_brand`, `device_model`,
                   `url_params`, `all_headers`, `original_request_url`,
                   `final_redirect_url`
            FROM `clicks`
            WHERE `id` IN :click_ids
              AND `click_time` < :archive_date
            """
        ).bindparams(bindparam("click_ids", expanding=True))
        delete_stmt = text(
            """
            DELETE FROM `clicks`
            WHERE `id` IN :click_ids
              AND `click_time` < :archive_date
            """
        ).bindparams(bindparam("click_ids", expanding=True))

        archived_total = 0
        deleted_total = 0
        batch_count = 0

        while True:
            retry_attempt = 0
            stop_after_empty_batch = False
            while True:
                try:
                    # 当前事务内锁定这一批源记录，避免并发归档/删除修改已选中的记录。
                    ids_result = await db.execute(
                        select_ids_stmt,
                        {
                            "archive_date": archive_date,
                            "high_water_id": high_water_id,
                            "batch_size": batch_size,
                        },
                    )
                    click_ids = [int(value) for value in ids_result.scalars().all()]

                    if not click_ids:
                        # 结束本轮空读事务；本轮高水位之后的新点击留待下一轮处理。
                        await db.commit()
                        stop_after_empty_batch = True
                        break

                    expected_count = len(click_ids)
                    archive_result = await db.execute(
                        insert_stmt,
                        {"click_ids": click_ids, "archive_date": archive_date},
                    )
                    archived_count = int(archive_result.rowcount or 0)
                    if archived_count != expected_count:
                        raise RuntimeError(
                            "点击归档批次写入数量不一致，已中止删除源记录："
                            f"批次={batch_count + 1}，待归档={expected_count}，实际写入={archived_count}"
                        )

                    delete_result = await db.execute(
                        delete_stmt,
                        {"click_ids": click_ids, "archive_date": archive_date},
                    )
                    deleted_count = int(delete_result.rowcount or 0)
                    if deleted_count != expected_count:
                        raise RuntimeError(
                            "点击归档批次删除数量不一致，当前批次事务已回滚："
                            f"批次={batch_count + 1}，待删除={expected_count}，实际删除={deleted_count}"
                        )

                    # 每批提交一次，限制事务持续时间、锁持有行数及 undo/redo 压力。
                    await db.commit()
                    archived_total += archived_count
                    deleted_total += deleted_count
                    batch_count += 1

                    if batch_count == 1 or batch_count % 10 == 0:
                        logger.info(
                            "点击归档批次进度：batches=%s archived=%s high_water_id=%s",
                            batch_count,
                            archived_total,
                            high_water_id,
                        )
                    break
                except Exception as exc:
                    # 仅回滚当前批次；此前已提交批次保持完整，下一次运行可从主表剩余记录续跑。
                    await db.rollback()
                    mysql_errno = get_mysql_errno(exc)
                    if mysql_errno in (1205, 1213) and retry_attempt < 3:
                        retry_attempt += 1
                        delay = 0.1 * (2 ** (retry_attempt - 1))
                        logger.warning(
                            "点击归档批次遇到 MySQL 锁等待超时/死锁，rollback 后重试："
                            "batch=%s attempt=%s/3 errno=%s delay=%.2fs",
                            batch_count + 1,
                            retry_attempt,
                            mysql_errno,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    logger.exception(
                        "点击归档批次失败：batch=%s archived_before_failure=%s",
                        batch_count + 1,
                        archived_total,
                    )
                    raise

            if stop_after_empty_batch:
                break

        return {
            "archived_count": archived_total,
            "deleted_count": deleted_total,
            "batch_count": batch_count,
            "high_water_id": high_water_id,
            "archive_date": archive_date_str,
            "skipped": False,
            "message": (
                f"成功归档 {archived_total} 条数据，分 {batch_count} 批完成"
                if archived_total
                else "没有需要归档的数据"
            ),
        }

    async def _ensure_archive_table(self, db: AsyncSession) -> None:
        """检查 clicks_archive 是否存在，不存在则按 DDL 创建。"""
        check_sql = text(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = 'clicks_archive'
            """
        )
        exists = (await db.execute(check_sql)).scalar() > 0
        if exists:
            return
        logger.info("归档表不存在，正在创建 clicks_archive ...")
        await db.execute(text(_CREATE_ARCHIVE_TABLE_SQL))
        await db.commit()


clicks_archive_service = ClicksArchiveService()
