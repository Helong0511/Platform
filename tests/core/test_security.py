import pytest
from datetime import timedelta

# 导入模块
from app.core.config import settings
from app.core.security import JWTUtils

# 直接修改settings属性，强制使用开发环境
settings.PRODUCTION_ENV = "development"

# 确保is_development属性被正确计算
settings.__dict__.pop("is_development", None)


class TestJWTUtils:
    """测试JWT工具类"""
    
    def test_create_access_token(self):
        """测试创建访问令牌"""
        # 使用RS256算法创建令牌
        user_id = 123
        token = JWTUtils.create_access_token(subject=user_id)
        
        # 验证令牌不为空
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_create_access_token_with_expires_delta(self):
        """测试使用自定义过期时间创建令牌"""
        # 设置10分钟过期
        expires_delta = timedelta(minutes=10)
        user_id = 456
        token = JWTUtils.create_access_token(subject=user_id, expires_delta=expires_delta)
        
        # 验证令牌不为空
        assert token is not None
        assert isinstance(token, str)
    
    @pytest.mark.asyncio
    async def test_verify_valid_token(self):
        """测试验证有效令牌"""
        # 生成一次密钥对，保存到settings中，确保创建和验证使用相同的密钥
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        
        # 生成2048位RSA密钥对
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # 序列化私钥
        private_key_str = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode("utf-8")
        
        # 序列化公钥
        public_key = private_key.public_key()
        public_key_str = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("utf-8")
        
        # 将密钥保存到settings中
        settings.RSA_PRIVATE_KEY = private_key_str
        settings.RSA_PUBLIC_KEY = public_key_str
        
        # 创建令牌
        user_id = 789
        token = JWTUtils.create_access_token(subject=user_id)
        
        # 验证令牌
        payload = await JWTUtils.verify_token(token)
        
        # 验证payload包含正确的信息
        assert payload is not None
        assert isinstance(payload, dict)
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "iat" in payload
        assert "exp" in payload
    
    @pytest.mark.asyncio
    async def test_verify_token_with_invalid_signature(self):
        """测试验证无效签名的令牌"""
        # 创建一个无效的令牌（手动修改签名部分）
        invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        
        # 验证应该失败
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            await JWTUtils.verify_token(invalid_token)
    
    @pytest.mark.asyncio
    async def test_verify_token_with_expired_token(self):
        """测试验证过期令牌"""
        # 创建一个已经过期的令牌（-1分钟过期）
        expires_delta = timedelta(minutes=-1)
        user_id = 101112
        token = JWTUtils.create_access_token(subject=user_id, expires_delta=expires_delta)
        
        # 验证应该失败，抛出过期异常
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            await JWTUtils.verify_token(token)
