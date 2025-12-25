import os

# 确保在导入应用之前设置开发环境
os.environ["PRODUCTION_ENV"] = "development"

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.main import app
from app.core.config import settings


@pytest.fixture
def client():
    """创建测试客户端"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client: TestClient):
    """获取认证头"""
    # 使用默认管理员账户进行登录
    login_data = {
        "username": settings.FIRST_SUPERUSER,
        "password": settings.FIRST_SUPERUSER_PASSWORD
    }
    
    response = client.post(f"{settings.API_V1_STR}/auth/login", data=login_data)
    token = response.json()["access_token"]
    
    return {
        "Authorization": f"Bearer {token}"
    }


class TestShortLinkAPI:
    """测试短链接相关API"""
    
    def test_generate_short_code(self, client: TestClient):
        """测试生成短链接代码"""
        response = client.get(f"{settings.API_V1_STR}/short-links/generate-code")
        
        assert response.status_code == 200
        assert "data" in response.json()
        assert "short_code" in response.json()["data"]
        assert len(response.json()["data"]["short_code"]) > 0
    
    def test_check_short_code_not_exists(self, client: TestClient):
        """测试检查不存在的短链接代码"""
        response = client.get(f"{settings.API_V1_STR}/short-links/check-code/nonexistent123")
        
        assert response.status_code == 200
        assert response.json()["data"]["exists"] is False
    
    def test_create_short_link(self, client: TestClient, auth_headers):
        """测试创建短链接"""
        short_link_data = {
            "original_url": "https://www.example.com",
            "title": "Test Link",
            "description": "A test link",
            "is_active": True
        }
        
        response = client.post(
            f"{settings.API_V1_STR}/short-links/",
            json=short_link_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json()["data"]["original_url"] == short_link_data["original_url"]
        assert response.json()["data"]["title"] == short_link_data["title"]
        assert "short_code" in response.json()["data"]
        
        # 保存创建的短链接ID，用于后续测试
        self.created_link_id = response.json()["data"]["id"]
        self.created_short_code = response.json()["data"]["short_code"]
    
    def test_check_short_code_exists(self, client: TestClient, auth_headers):
        """测试检查已存在的短链接代码"""
        # 先创建一个短链接
        short_link_data = {
            "original_url": "https://www.example.com/check",
            "title": "Check Link",
            "short_code": "test123"
        }
        
        client.post(
            f"{settings.API_V1_STR}/short-links/",
            json=short_link_data,
            headers=auth_headers
        )
        
        # 检查短链接代码是否存在
        response = client.get(f"{settings.API_V1_STR}/short-links/check-code/test123")
        
        assert response.status_code == 200
        assert response.json()["data"]["exists"] is True
    
    def test_get_short_links_list(self, client: TestClient, auth_headers):
        """测试获取短链接列表"""
        response = client.get(
            f"{settings.API_V1_STR}/short-links/",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert "data" in response.json()
        assert isinstance(response.json()["data"], list)
        assert "total" in response.json()
        assert "page" in response.json()
        assert "page_size" in response.json()
    
    def test_get_short_link_detail(self, client: TestClient, auth_headers):
        """测试获取短链接详情"""
        # 先创建一个短链接
        short_link_data = {
            "original_url": "https://www.example.com/detail",
            "title": "Detail Link"
        }
        
        create_response = client.post(
            f"{settings.API_V1_STR}/short-links/",
            json=short_link_data,
            headers=auth_headers
        )
        
        link_id = create_response.json()["data"]["id"]
        
        # 获取短链接详情
        response = client.get(
            f"{settings.API_V1_STR}/short-links/{link_id}/detail",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert "data" in response.json()
        assert response.json()["data"]["id"] == link_id
        assert response.json()["data"]["original_url"] == short_link_data["original_url"]
    
    def test_update_short_link(self, client: TestClient, auth_headers):
        """测试更新短链接"""
        # 先创建一个短链接
        short_link_data = {
            "original_url": "https://www.example.com/update",
            "title": "Update Link"
        }
        
        create_response = client.post(
            f"{settings.API_V1_STR}/short-links/",
            json=short_link_data,
            headers=auth_headers
        )
        
        link_id = create_response.json()["data"]["id"]
        
        # 更新短链接
        update_data = {
            "title": "Updated Link",
            "description": "Updated description"
        }
        
        response = client.put(
            f"{settings.API_V1_STR}/short-links/{link_id}",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json()["data"]["title"] == update_data["title"]
        assert response.json()["data"]["description"] == update_data["description"]
    
    def test_delete_short_link(self, client: TestClient, auth_headers):
        """测试删除短链接"""
        # 先创建一个短链接
        short_link_data = {
            "original_url": "https://www.example.com/delete",
            "title": "Delete Link"
        }
        
        create_response = client.post(
            f"{settings.API_V1_STR}/short-links/",
            json=short_link_data,
            headers=auth_headers
        )
        
        link_id = create_response.json()["data"]["id"]
        
        # 删除短链接
        response = client.delete(
            f"{settings.API_V1_STR}/short-links/{link_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json()["data"]["message"] == "短链接已删除"
        
        # 验证短链接已被删除
        detail_response = client.get(
            f"{settings.API_V1_STR}/short-links/{link_id}/detail",
            headers=auth_headers
        )
        
        assert detail_response.status_code == 404
    
    def test_get_short_link_stats(self, client: TestClient, auth_headers):
        """测试获取短链接统计"""
        response = client.get(
            f"{settings.API_V1_STR}/short-links/stats/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert "data" in response.json()
        assert "total_links" in response.json()["data"]
        assert "total_clicks" in response.json()["data"]
        assert "active_links" in response.json()["data"]
        assert "expired_links" in response.json()["data"]
    
    def test_short_link_redirect(self, client: TestClient, auth_headers):
        """测试短链接重定向"""
        # 先创建一个短链接
        short_link_data = {
            "original_url": "https://www.example.com/redirect",
            "title": "Redirect Link"
        }
        
        create_response = client.post(
            f"{settings.API_V1_STR}/short-links/",
            json=short_link_data,
            headers=auth_headers
        )
        
        short_code = create_response.json()["data"]["short_code"]
        
        # 测试重定向
        response = client.get(
            f"{settings.API_V1_STR}/short-links/{short_code}",
            follow_redirects=False
        )
        
        assert response.status_code == 302
        assert response.headers["location"] == short_link_data["original_url"]
    
    def test_create_short_link_with_custom_code(self, client: TestClient, auth_headers):
        """测试使用自定义短链接代码创建短链接"""
        custom_code = "custom123"
        short_link_data = {
            "original_url": "https://www.example.com/custom",
            "title": "Custom Link",
            "short_code": custom_code
        }
        
        response = client.post(
            f"{settings.API_V1_STR}/short-links/",
            json=short_link_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json()["data"]["short_code"] == custom_code
    
    def test_create_short_link_with_expiry(self, client: TestClient, auth_headers):
        """测试创建带有过期时间的短链接"""
        # 设置过期时间为2小时后
        expires_at = (datetime.now() + timedelta(hours=2)).isoformat()
        
        short_link_data = {
            "original_url": "https://www.example.com/expiry",
            "title": "Expiry Link",
            "expires_at": expires_at
        }
        
        response = client.post(
            f"{settings.API_V1_STR}/short-links/",
            json=short_link_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert "expires_at" in response.json()["data"]
        assert response.json()["data"]["expires_at"] is not None
