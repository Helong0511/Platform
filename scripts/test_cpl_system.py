"""
CPL 系统测试脚本
用于验证系统功能是否正常
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import AsyncSessionLocal
from app.models.models import (
    Advertiser, Publisher, Offer, Click, OfferCap, OfferDiscount,
    AdvertiserTest, AffiliateTest, PostbackConversion
)
from sqlalchemy.future import select
from sqlalchemy import func


async def test_models():
    """测试数据模型是否正确加载"""
    print("=" * 50)
    print("测试数据模型...")
    print("=" * 50)
    
    async with AsyncSessionLocal() as db:
        # 测试查询（不返回数据，只验证表是否存在）
        try:
            result = await db.execute(select(func.count(Advertiser.id)))
            count = result.scalar() or 0
            print(f"✅ Advertiser 模型正常，当前记录数: {count}")
        except Exception as e:
            print(f"❌ Advertiser 模型错误: {str(e)}")
            return False
        
        try:
            result = await db.execute(select(func.count(Publisher.id)))
            count = result.scalar() or 0
            print(f"✅ Publisher 模型正常，当前记录数: {count}")
        except Exception as e:
            print(f"❌ Publisher 模型错误: {str(e)}")
            return False
        
        try:
            result = await db.execute(select(func.count(Offer.id)))
            count = result.scalar() or 0
            print(f"✅ Offer 模型正常，当前记录数: {count}")
        except Exception as e:
            print(f"❌ Offer 模型错误: {str(e)}")
            return False
        
        try:
            result = await db.execute(select(func.count(Click.id)))
            count = result.scalar() or 0
            print(f"✅ Click 模型正常，当前记录数: {count}")
        except Exception as e:
            print(f"❌ Click 模型错误: {str(e)}")
            return False
        
        try:
            result = await db.execute(select(func.count(OfferCap.id)))
            count = result.scalar() or 0
            print(f"✅ OfferCap 模型正常，当前记录数: {count}")
        except Exception as e:
            print(f"❌ OfferCap 模型错误: {str(e)}")
            return False
        
        try:
            result = await db.execute(select(func.count(OfferDiscount.id)))
            count = result.scalar() or 0
            print(f"✅ OfferDiscount 模型正常，当前记录数: {count}")
        except Exception as e:
            print(f"❌ OfferDiscount 模型错误: {str(e)}")
            return False
        
        # 检查 PostbackConversion 新字段
        try:
            result = await db.execute(select(PostbackConversion).limit(1))
            conversion = result.scalars().first()
            if conversion:
                has_click_id = hasattr(conversion, 'click_id')
                has_click_time = hasattr(conversion, 'click_time')
                has_status = hasattr(conversion, 'conversion_status')
                print(f"✅ PostbackConversion 模型检查:")
                print(f"   - click_id 字段: {'✅' if has_click_id else '❌'}")
                print(f"   - click_time 字段: {'✅' if has_click_time else '❌'}")
                print(f"   - conversion_status 字段: {'✅' if has_status else '❌'}")
            else:
                # 没有记录，直接检查模型定义
                print(f"✅ PostbackConversion 模型检查:")
                print(f"   - click_id 字段: {'✅' if hasattr(PostbackConversion, 'click_id') else '❌'}")
                print(f"   - click_time 字段: {'✅' if hasattr(PostbackConversion, 'click_time') else '❌'}")
                print(f"   - conversion_status 字段: {'✅' if hasattr(PostbackConversion, 'conversion_status') else '❌'}")
        except Exception as e:
            print(f"❌ PostbackConversion 模型错误: {str(e)}")
            return False
    
    return True


async def test_core_modules():
    """测试核心模块是否可以正常导入"""
    print("\n" + "=" * 50)
    print("测试核心模块...")
    print("=" * 50)
    
    try:
        from app.core.tracking import (
            generate_click_id,
            generate_unique_click_id,
            generate_click_id_from_timestamp,
            generate_upstream_tracklink,
            generate_downstream_tracklink
        )
        print("✅ 点击追踪模块导入成功")
    except Exception as e:
        print(f"❌ 点击追踪模块导入失败: {str(e)}")
        return False
    
    try:
        from app.core.cap import check_cap, increment_cap_count, reset_daily_caps
        print("✅ Cap 管理模块导入成功")
    except Exception as e:
        print(f"❌ Cap 管理模块导入失败: {str(e)}")
        return False
    
    try:
        from app.core.discount import calculate_discount, get_discount_info
        print("✅ 扣量管理模块导入成功")
    except Exception as e:
        print(f"❌ 扣量管理模块导入失败: {str(e)}")
        return False
    
    return True


async def main():
    """主测试函数"""
    print("\n" + "=" * 50)
    print("CPL 系统测试")
    print("=" * 50 + "\n")
    
    # 测试数据模型
    models_ok = await test_models()
    
    # 测试核心模块
    modules_ok = await test_core_modules()
    
    print("\n" + "=" * 50)
    if models_ok and modules_ok:
        print("✅ 所有测试通过！")
        print("=" * 50)
        return 0
    else:
        print("❌ 部分测试失败，请检查错误信息")
        print("=" * 50)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

