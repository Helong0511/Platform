import os
import logging

# 设置日志级别为DEBUG
logging.basicConfig(level=logging.DEBUG)

print("开始设置环境变量...")
os.environ["PRODUCTION_ENV"] = "development"

print("开始导入依赖...")
from fastapi import Request, Depends
from fastapi.security import OAuth2PasswordRequestForm
from starlette.testclient import TestClient
from app.main import app
from app.core.config import settings

print(f"配置信息: ")
print(f"  FIRST_SUPERUSER: {settings.FIRST_SUPERUSER}")
print(f"  FIRST_SUPERUSER_PASSWORD: {settings.FIRST_SUPERUSER_PASSWORD}")
print(f"  注意：测试中将使用固定的用户名 'admin' 和密码 'My@SecurePssw0rd2025!' 进行测试")

print("创建测试客户端...")
client = TestClient(app)

print("开始发送登录请求...")
# 使用固定的用户名和密码测试
login_username = "admin"
login_password = "My@SecurePssw0rd2025!"

# 使用data参数发送请求，这是OAuth2PasswordRequestForm期望的格式
response = client.post(
    "/api/v1/auth/login",
    data={
        "username": login_username,
        "password": login_password
    }
)

print("\n=== 响应结果 ===")
print(f"状态码: {response.status_code}")
print(f"响应头: {dict(response.headers)}")
print(f"响应内容: {repr(response.text)}")

# 尝试直接测试OAuth2PasswordRequestForm的解析
print("\n=== 测试OAuth2PasswordRequestForm解析 ===")

# 创建一个简单的FastAPI应用来测试
from fastapi import FastAPI

app2 = FastAPI()

@app2.post("/test-form")
async def test_form(form_data: OAuth2PasswordRequestForm = Depends()):
    return {
        "username": form_data.username,
        "password": form_data.password,
        "scope": form_data.scopes,
        "grant_type": form_data.grant_type
    }

client2 = TestClient(app2)

response2 = client2.post(
    "/test-form",
    data={
        "username": "test_user",
        "password": "test_password"
    }
)

print(f"测试表单状态码: {response2.status_code}")
print(f"测试表单响应: {response2.json()}")
