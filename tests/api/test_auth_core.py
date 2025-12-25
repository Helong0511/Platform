import os
import logging

# 设置日志级别为DEBUG
logging.basicConfig(level=logging.DEBUG)

print("开始设置环境变量...")
os.environ["PRODUCTION_ENV"] = "development"

print("开始导入依赖...")
from app.core.config import settings
from app.core.security import JWTUtils
from app.core.database import AsyncSessionLocal, init_db
from app.models.models import User
import asyncio

print(f"配置信息: ")
print(f"  FIRST_SUPERUSER: {settings.FIRST_SUPERUSER}")
print(f"  FIRST_SUPERUSER_PASSWORD: {settings.FIRST_SUPERUSER_PASSWORD}")

# 直接测试数据库操作
async def test_db():
    print("\n=== 测试数据库连接 ===")
    async with AsyncSessionLocal() as session:
        # 查询用户
        from sqlalchemy.future import select
        result = await session.execute(
            select(User).where(User.username == settings.FIRST_SUPERUSER)
        )
        user = result.scalars().first()
        
        if user:
            print(f"用户存在: {user.username}")
            print(f"用户ID: {user.id}")
            print(f"用户角色: {user.role}")
            print(f"用户激活状态: {user.is_active}")
        else:
            print("用户不存在，初始化数据库...")
            await init_db()
            # 再次查询
            result = await session.execute(
                select(User).where(User.username == settings.FIRST_SUPERUSER)
            )
            user = result.scalars().first()
            if user:
                print(f"用户已创建: {user.username}")
            else:
                print("用户创建失败")
        
        # 测试密码验证
        if user:
            print(f"\n测试密码验证:")
            is_valid = user.verify_password(settings.FIRST_SUPERUSER_PASSWORD)
            print(f"密码验证结果: {is_valid}")
            
            # 测试JWT生成
            print(f"\n测试JWT生成:")
            token = JWTUtils.create_access_token(user.id)
            print(f"生成的token: {token}")
            
            # 测试JWT验证
            print(f"\n测试JWT验证:")
            payload = JWTUtils.decode_access_token(token)
            print(f"解码后的payload: {payload}")

# 运行测试
asyncio.run(test_db())
