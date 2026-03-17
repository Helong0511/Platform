#!/usr/bin/env python3
"""
检查转化记录数据的脚本
"""
import asyncio
from sqlalchemy import select, func
from app.core.database import AsyncSessionLocal
from app.models.models import PostbackConversion

async def check_conversion_data():
    """检查转化记录数据"""
    print("开始检查转化记录数据...")
    
    async with AsyncSessionLocal() as session:
        try:
            # 查询最近10条转化记录
            stmt = select(PostbackConversion).order_by(PostbackConversion.created_at.desc()).limit(10)
            result = await session.execute(stmt)
            conversions = result.scalars().all()
            
            print(f"\n最近10条转化记录:")
            print("-" * 100)
            print(f"{'ID':<5} {'平台':<10} {'转化ID':<30} {'创建时间':<20} {'状态':<15}")
            print("-" * 100)
            
            for conv in conversions:
                status = getattr(conv, 'conversion_status', 'N/A')
                created_at = conv.created_at.strftime('%Y-%m-%d %H:%M:%S') if conv.created_at else 'N/A'
                print(f"{conv.id:<5} {conv.platform:<10} {conv.conversion_id:<30} {created_at:<20} {status:<15}")
            
            # 统计总数
            count_stmt = select(func.count(PostbackConversion.id))
            count_result = await session.execute(count_stmt)
            total_count = count_result.scalar()
            print(f"\n总转化记录数: {total_count}")
            
            # 按平台统计
            platform_stmt = select(PostbackConversion.platform, func.count(PostbackConversion.id).label('count')).group_by(PostbackConversion.platform).order_by(func.count(PostbackConversion.id).desc())
            platform_result = await session.execute(platform_stmt)
            platform_rows = platform_result.all()
            
            print(f"\n按平台统计:")
            print("-" * 50)
            print(f"{'平台':<15} {'数量':<10}")
            print("-" * 50)
            for row in platform_rows:
                print(f"{row.platform:<15} {row.count:<10}")
                
        except Exception as e:
            print(f"查询失败: {e}")

if __name__ == "__main__":
    asyncio.run(check_conversion_data())
