import os
import logging

# 设置日志级别为DEBUG
logging.basicConfig(level=logging.DEBUG)

print("开始设置环境变量...")
os.environ["PRODUCTION_ENV"] = "development"
print(f"环境变量设置完成: PRODUCTION_ENV={os.environ['PRODUCTION_ENV']}")

print("开始导入TestClient...")
from fastapi.testclient import TestClient
print("TestClient导入完成")

print("开始导入app...")
from app.main import app
print("app导入完成")

print("开始导入settings...")
from app.core.config import settings
print("settings导入完成")

print(f"配置信息: ")
print(f"  FIRST_SUPERUSER: {settings.FIRST_SUPERUSER}")
print(f"  FIRST_SUPERUSER_PASSWORD: {settings.FIRST_SUPERUSER_PASSWORD}")
print(f"  API_V1_STR: {settings.API_V1_STR}")

print("创建测试客户端...")
client = TestClient(app)
print("测试客户端创建完成")

print("开始发送登录请求...")
# 使用postman风格的请求，获取详细的响应信息
response = client.post(
    "/api/v1/auth/login",
    data={
        "username": settings.FIRST_SUPERUSER,
        "password": settings.FIRST_SUPERUSER_PASSWORD
    },
    headers={
        "Content-Type": "application/x-www-form-urlencoded"
    }
)

print("\n=== 响应结果 ===")
print(f"状态码: {response.status_code}")
print(f"响应头: {dict(response.headers)}")
print(f"响应内容长度: {len(response.text)}")
print(f"响应内容: {repr(response.text)}")  # 使用repr确保可以看到所有字符
try:
    json_data = response.json()
    print(f"响应JSON: {json_data}")
except Exception as e:
    print(f"解析JSON失败: {e}")
    print(f"异常类型: {type(e).__name__}")

# 尝试使用不同的请求格式
print("\n=== 尝试使用json参数发送请求 ===")
response2 = client.post(
    "/api/v1/auth/login",
    json={
        "username": settings.FIRST_SUPERUSER,
        "password": settings.FIRST_SUPERUSER_PASSWORD
    }
)
print(f"状态码: {response2.status_code}")
print(f"响应内容: {repr(response2.text)}")

print("\n=== 测试结束 ===")
