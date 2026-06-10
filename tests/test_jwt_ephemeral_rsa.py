"""JWT 临时 RSA 密钥对一致性测试"""
from jose import jwt

from app.core.config import settings
from app.core.security import JWTUtils


def test_ephemeral_rsa_sign_and_verify():
    token = JWTUtils.create_access_token("1")
    payload = jwt.decode(
        token,
        JWTUtils._load_rsa_key(
            settings.RSA_PUBLIC_KEY,
            settings.RSA_PUBLIC_KEY_PATH,
            "public",
        ),
        algorithms=[settings.JWT_ALGORITHM],
        options={"verify_aud": False},
    )
    assert payload["sub"] == "1"
