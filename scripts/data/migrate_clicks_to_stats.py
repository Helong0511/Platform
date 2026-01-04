"""
将已有转化的点击记录迁移到 click_stats 表
只迁移在 postback_conversions 表中有对应记录的点击
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlalchemy import text
from app.core.database import AsyncSessionLocal
from app.models.models import Base
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings


async def migrate_converted_clicks_to_stats():
    """迁移已有转化的点击数据到统计表"""
    print("开始迁移已有转化的点击记录到 click_stats 表...")
    
    async with AsyncSessionLocal() as db:
        try:
            # 1. 检查 click_stats 表是否存在，如果不存在则创建
            check_table_sql = text("""
                SELECT COUNT(*) as count
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = 'click_stats'
            """)
            result = await db.execute(check_table_sql)
            table_exists = result.scalar() > 0
            
            if not table_exists:
                print("click_stats 表不存在，正在创建...")
                # 使用 SQLAlchemy 创建表
                engine = create_async_engine(str(settings.SQLALCHEMY_DATABASE_URI))
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                print("click_stats 表创建成功")
            
            # 2. 检查 postback_conversions 表是否有 click_id 字段
            check_column_sql = text("""
                SELECT COUNT(*) as count
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = 'postback_conversions'
                  AND column_name = 'click_id'
            """)
            column_result = await db.execute(check_column_sql)
            has_click_id_column = column_result.scalar() > 0
            
            if not has_click_id_column:
                print("警告: postback_conversions 表中没有 click_id 字段")
                print("这意味着数据库表可能是旧版本，需要先添加 click_id 字段")
                print("或者这些转化记录还没有关联到点击记录")
                print("跳过迁移（新接收的 postback 数据会自动创建 ClickStats 记录）")
                return {
                    "migrated_count": 0,
                    "message": "postback_conversions 表缺少 click_id 字段，跳过迁移"
                }
            
            # 3. 统计需要迁移的数据量
            count_sql = text("""
                SELECT COUNT(DISTINCT c.`click_id`) as count
                FROM `clicks` c
                INNER JOIN `postback_conversions` pc ON c.`click_id` = pc.`click_id`
                WHERE pc.`click_id` IS NOT NULL
                  AND c.`click_id` NOT IN (SELECT `click_id` FROM `click_stats`)
            """)
            count_result = await db.execute(count_sql)
            total_count = count_result.scalar() or 0
            
            if total_count == 0:
                print("没有需要迁移的数据（所有有转化的点击记录已存在于 click_stats 表中）")
                return {
                    "migrated_count": 0,
                    "message": "没有需要迁移的数据"
                }
            
            print(f"发现 {total_count} 条需要迁移的记录")
            
            # 4. 迁移数据：只迁移有转化的点击记录
            migrate_sql = text("""
                INSERT IGNORE INTO `click_stats` 
                (`click_id`, `offer_id`, `publisher_id`, `advertiser_id`, `click_time`, `created_at`)
                SELECT DISTINCT
                    c.`click_id`,
                    c.`offer_id`,
                    c.`publisher_id`,
                    c.`advertiser_id`,
                    c.`click_time`,
                    c.`created_at`
                FROM `clicks` c
                INNER JOIN `postback_conversions` pc ON c.`click_id` = pc.`click_id`
                WHERE pc.`click_id` IS NOT NULL
                  AND c.`click_id` NOT IN (SELECT `click_id` FROM `click_stats`)
            """)
            
            result = await db.execute(migrate_sql)
            migrated_count = result.rowcount
            await db.commit()
            
            print(f"迁移完成，共迁移 {migrated_count} 条记录")
            
            return {
                "migrated_count": migrated_count,
                "total_count": total_count,
                "message": f"成功迁移 {migrated_count} 条记录"
            }
            
        except Exception as e:
            await db.rollback()
            print(f"迁移失败: {e}")
            import traceback
            traceback.print_exc()
            raise


async def main():
    """主函数"""
    try:
        result = await migrate_converted_clicks_to_stats()
        print(f"\n迁移结果: {result['message']}")
        if result.get('migrated_count', 0) > 0:
            print(f"迁移记录数: {result['migrated_count']}")
        elif '缺少 click_id 字段' in result.get('message', ''):
            print("\n提示: 如果需要迁移历史数据，请先运行以下 SQL 添加 click_id 字段:")
            print("   mysql -u用户名 -p数据库名 < scripts/data/add_click_id_to_postback_conversions.sql")
            print("   或者手动执行:")
            print("   ALTER TABLE postback_conversions")
            print("   ADD COLUMN click_id VARCHAR(255) NULL COMMENT '关联的Click ID' AFTER client_id,")
            print("   ADD INDEX idx_postback_click_id (click_id);")
    except Exception as e:
        print(f"执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

