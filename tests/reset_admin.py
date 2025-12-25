import os
import logging

# 设置日志级别为DEBUG
logging.basicConfig(level=logging.DEBUG)

print("开始设置环境变量...")
os.environ["PRODUCTION_ENV"] = "development"

print("开始导入依赖...")
from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.models.models import User, UserRole
import asyncio

print(f"配置信息: ")
print(f"  FIRST_SUPERUSER: {settings.FIRST_SUPERUSER}")
print(f"  FIRST_SUPERUSER_PASSWORD: {settings.FIRST_SUPERUSER_PASSWORD}")

# 直接测试数据库操作
async def reset_admin():
    print("\n=== 重置管理员用户 ===")
    async with AsyncSessionLocal() as session:
        # 查询现有用户
        from sqlalchemy.future import select
        from sqlalchemy import delete
        
        # 删除现有管理员用户
        result = await session.execute(
            delete(User).where(User.username == settings.FIRST_SUPERUSER)
        )
        await session.commit()
        print(f"已删除现有管理员用户: {result.rowcount} 行受影响")
        
        # 创建新的管理员用户
        admin = User(
            username=settings.FIRST_SUPERUSER,
            email=f"{settings.FIRST_SUPERUSER}@example.com",
            role=UserRole.ADMIN,
            is_active=True,
            login_restricted=False
        )
        # 使用set_password方法设置密码
        admin.set_password(settings.FIRST_SUPERUSER_PASSWORD)
        session.add(admin)
        await session.commit()
        print(f"已创建新的管理员用户: {admin.username}")
        
        # 测试密码验证
        print(f"\n测试密码验证:")
        is_valid = admin.verify_password(settings.FIRST_SUPERUSER_PASSWORD)
        print(f"密码验证结果: {is_valid}")
        
        # 重新查询用户
        result = await session.execute(
            select(User).where(User.username == settings.FIRST_SUPERUSER)
        )
        user = result.scalars().first()
        if user:
            print(f"\n重新查询用户:")
            print(f"用户ID: {user.id}")
            print(f"用户名: {user.username}")
            print(f"密码哈希: {user.hashed_password}")
            # 再次测试密码验证
            is_valid2 = user.verify_password(settings.FIRST_SUPERUSER_PASSWORD)
            print(f"再次验证密码结果: {is_valid2}")

# 运行测试
asyncio.run(reset_admin())
