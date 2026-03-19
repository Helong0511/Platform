import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DatabaseIp = "43.156.101.243"
DatabaseUser = "remote"
DatabasePassword = "kb7$rL3d8!tQ"
DatabasePort = 3306
DatabaseName = "platform"

async def check_conversion_stats():
    # 创建异步引擎（使用正确的数据库连接信息）
    engine = create_async_engine(f"mysql+aiomysql://{DatabaseUser}:{DatabasePassword}@{DatabaseIp}:{DatabasePort}/{DatabaseName}")
    
    try:
        async with engine.connect() as conn:
            # 检查postback_conversions表结构
            print("=== postback_conversions 表结构 ===")
            result = await conn.execute(text('DESCRIBE postback_conversions'))
            for row in result.all():
                print(row)
            
            # 统计总转化记录数
            print("\n=== 总转化记录数 ===")
            result = await conn.execute(text('SELECT COUNT(*) FROM postback_conversions'))
            count = result.scalar()
            print(f'总转化记录数: {count}')
            
            # 按offer分组统计转化数量
            print("\n=== 按offer分组的转化数量 ===")
            result = await conn.execute(
                text('''
                SELECT c.offer_id, COUNT(p.id) as conversion_count
                FROM postback_conversions p
                JOIN clicks c ON p.click_id = c.click_id
                GROUP BY c.offer_id
                ORDER BY conversion_count DESC
                ''')
            )
            for row in result.all():
                print(f'offer_id: {row[0]}, 转化数量: {row[1]}')
                
            # 检查指定日期范围内的转化数据
            print("\n=== 2026-03-10 到 2026-03-17 期间的转化数据 ===")
            result = await conn.execute(
                text('''
                SELECT c.offer_id, COUNT(p.id) as conversion_count
                FROM postback_conversions p
                JOIN clicks c ON p.click_id = c.click_id
                WHERE p.created_at BETWEEN '2026-03-10 00:00:00' AND '2026-03-17 23:59:59'
                GROUP BY c.offer_id
                ORDER BY conversion_count DESC
                ''')
            )
            for row in result.all():
                print(f'offer_id: {row[0]}, 转化数量: {row[1]}')
                
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_conversion_stats())