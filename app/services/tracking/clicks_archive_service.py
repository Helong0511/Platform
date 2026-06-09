"""
点击记录归档服务（主表 clicks → clicks_archive）。

职责：
- 将 click_time 早于保留期的记录 INSERT IGNORE 至归档表后 DELETE 主表
- 归档表不存在时自动 CREATE；令牌模式且主表为空时跳过

默认保留 90 天；由定时任务 archive_old_clicks 调用模块单例 clicks_archive_service。
"""
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
    """
    点击数据冷热分离服务。

    使用 INSERT IGNORE 避免主键冲突后 DELETE 主表；
    模块级单例 clicks_archive_service 供定时任务直接调用。
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

    async def archive_old_clicks(self, db: AsyncSession, days: int = 90) -> Dict[str, Any]:
        """
        归档并清理过期点击记录。

        流程：计算 cutoff → 跳过判断 → 确保归档表存在 → 统计待归档数 →
        INSERT IGNORE 到 clicks_archive → DELETE 主表 → commit。

        Args:
            db: 数据库会话
            days: 保留最近 N 天，默认 90

        Returns:
            含 archived_count、deleted_count、archive_date、skipped、message 的统计字典
        """
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

        # ====== 迁移：INSERT IGNORE 防重复，再 DELETE 主表 ======
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
