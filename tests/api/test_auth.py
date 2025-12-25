import os

# 确保在导入应用之前设置开发环境
os.environ["PRODUCTION_ENV"] = "development"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings


@pytest.fixture
def client():
    """创建测试客户端"""
    with TestClient(app) as c:
        yield c


class TestAuthAPI:
    """测试认证相关API"""
    
    def test_login_with_valid_credentials(self, client: TestClient):
        """测试使用有效凭证登录"""
        # 使用默认管理员账户进行测试
        login_data = {
            "username": settings.FIRST_SUPERUSER,
            "password": settings.FIRST_SUPERUSER_PASSWORD
        }
        
        response = client.post("/api/v1/auth/login", data=login_data)
        
        # 验证响应
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.json()["token_type"] == "bearer"
    
    def test_login_with_invalid_credentials(self, client: TestClient):
        """测试使用无效凭证登录"""
        login_data = {
            "username": "invalid_user",
            "password": "invalid_password"
        }
        
        response = client.post("/api/v1/auth/login", data=login_data)
        
        # 验证响应
        assert response.status_code == 401
        assert "detail" in response.json()
    
    def test_get_current_user(self, client: TestClient):
        """测试获取当前用户信息"""
        # 先登录获取token
        login_data = {
            "username": settings.FIRST_SUPERUSER,
            "password": settings.FIRST_SUPERUSER_PASSWORD
        }
        login_response = client.post("/api/v1/auth/login", data=login_data)
        token = login_response.json()["access_token"]
        
        # 使用token获取当前用户信息
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # 验证响应
        assert response.status_code == 200
        assert response.json()["data"]["username"] == settings.FIRST_SUPERUSER
    
    def test_get_current_user_with_invalid_token(self, client: TestClient):
        """测试使用无效token获取当前用户信息"""
        invalid_token = "invalid_token"
        
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {invalid_token}"}
        )
        
        # 验证响应
        assert response.status_code == 401
        assert "detail" in response.json()
