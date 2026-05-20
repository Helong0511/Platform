"""点击记录归档（主表 -> clicks_archive）。"""
import logging
from datetime import timedelta
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    """将过期 clicks 迁移至 clicks_archive 并删除主表数据。"""

    async def count_clicks(self, db: AsyncSession) -> int:
        result = await db.execute(text("SELECT COUNT(*) FROM `clicks`"))
        return int(result.scalar() or 0)

    async def should_skip_archive(self, db: AsyncSession) -> bool:
        """
        令牌模式且主表无数据时跳过（新流量不再写 clicks，仅保留历史清理能力）。
        """
        if should_persist_clicks_to_db():
            return False
        return await self.count_clicks(db) == 0

    async def archive_old_clicks(self, db: AsyncSession, days: int = 90) -> Dict[str, Any]:
        now = get_app_now_naive()
        archive_date = now - timedelta(days=days)
        archive_date_str = archive_date.strftime("%Y-%m-%d %H:%M:%S")

        if await self.should_skip_archive(db):
            logger.info("点击不落库模式且主表为空，跳过归档任务")
            return {
                "archived_count": 0,
                "deleted_count": 0,
                "archive_date": archive_date_str,
                "skipped": True,
                "message": "点击不落库模式，主表无数据，已跳过归档",
            }

        await self._ensure_archive_table(db)

        count_result = await db.execute(
            text(
                "SELECT COUNT(*) FROM `clicks` WHERE `click_time` < :archive_date"
            ),
            {"archive_date": archive_date},
        )
        total_count = int(count_result.scalar() or 0)

        if total_count == 0:
            return {
                "archived_count": 0,
                "deleted_count": 0,
                "archive_date": archive_date_str,
                "skipped": False,
                "message": "没有需要归档的数据",
            }

        logger.info("发现 %s 条需要归档的点击记录", total_count)

        archive_result = await db.execute(
            text(
                """
                INSERT IGNORE INTO `clicks_archive`
                (`id`, `click_id`, `offer_id`, `publisher_id`, `advertiser_id`,
                 `short_link_id`, `click_time`, `ip`, `device`, `country`,
                 `user_agent`, `referer`, `conversion_id`, `created_at`,
                 `os`, `os_version`, `browser`, `browser_version`,
                 `accept_language`, `accept_encoding`, `is_bot`,
                 `device_type`, `device_brand`, `device_model`,
                 `url_params`, `all_headers`)
                SELECT `id`, `click_id`, `offer_id`, `publisher_id`, `advertiser_id`,
                       `short_link_id`, `click_time`, `ip`, `device`, `country`,
                       `user_agent`, `referer`, `conversion_id`, `created_at`,
                       `os`, `os_version`, `browser`, `browser_version`,
                       `accept_language`, `accept_encoding`, `is_bot`,
                       `device_type`, `device_brand`, `device_model`,
                       `url_params`, `all_headers`
                FROM `clicks`
                WHERE `click_time` < :archive_date
                """
            ),
            {"archive_date": archive_date},
        )
        archived_count = archive_result.rowcount

        delete_result = await db.execute(
            text("DELETE FROM `clicks` WHERE `click_time` < :archive_date"),
            {"archive_date": archive_date},
        )
        deleted_count = delete_result.rowcount

        await db.commit()

        return {
            "archived_count": archived_count,
            "deleted_count": deleted_count,
            "archive_date": archive_date_str,
            "skipped": False,
            "message": f"成功归档 {archived_count} 条数据",
        }

    async def _ensure_archive_table(self, db: AsyncSession) -> None:
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
