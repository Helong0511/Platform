import os
import logging

# 设置日志级别为DEBUG
logging.basicConfig(level=logging.DEBUG)

print("开始设置环境变量...")
os.environ["PRODUCTION_ENV"] = "development"

print("开始导入依赖...")
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

print(f"配置信息: ")
print(f"  FIRST_SUPERUSER: {settings.FIRST_SUPERUSER}")
print(f"  FIRST_SUPERUSER_PASSWORD: {settings.FIRST_SUPERUSER_PASSWORD}")

print("创建测试客户端...")
client = TestClient(app)

print("开始发送登录请求...")
# 使用data参数发送请求，这是OAuth2PasswordRequestForm期望的格式
response = client.post(
    "/api/v1/auth/login",
    data={
        "username": settings.FIRST_SUPERUSER,
        "password": settings.FIRST_SUPERUSER_PASSWORD
    }
)

print("\n=== 响应结果 ===")
print(f"状态码: {response.status_code}")
print(f"响应头: {dict(response.headers)}")
print(f"响应内容长度: {len(response.text)}")
print(f"响应内容: {repr(response.text)}")

# 尝试解析响应
print("\n=== 解析响应 ===")
try:
    json_data = response.json()
    print(f"响应JSON: {json_data}")
except Exception as e:
    print(f"解析JSON失败: {e}")
    print(f"异常类型: {type(e).__name__}")
    # 查看响应内容的详细信息
    print(f"响应内容的前100个字符: {repr(response.text[:100])}")
    print(f"响应内容的后100个字符: {repr(response.text[-100:])}")

# 尝试直接访问docs，看看API是否正常运行
print("\n=== 测试API文档访问 ===")
response_docs = client.get("/api/v1/docs")
print(f"Docs状态码: {response_docs.status_code}")

# 检查API路由是否正确注册
print("\n=== 检查API路由 ===")
from fastapi.openapi.utils import get_openapi

openapi_schema = get_openapi(
    title=app.title,
    version=app.version,
    openapi_version=app.openapi_version,
    description=app.description,
    routes=app.routes,
)

# 查找登录路由
login_path = "/api/v1/auth/login"
paths = openapi_schema.get("paths", {})
print(f"API路径: {list(paths.keys())}")
print(f"登录路径存在: {login_path in paths}")
if login_path in paths:
    print(f"登录路径方法: {list(paths[login_path].keys())}")
