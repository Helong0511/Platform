"""
JWT 编解码封装（基于 PyJWT）。

统一替代 python-jose，显式限制 algorithms，降低算法混淆风险。
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

import jwt
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidSignatureError,
    InvalidTokenError,
    PyJWTError,
)

# 兼容原 python-jose 异常类型命名
JWTError = PyJWTError
JWSError = InvalidSignatureError
JWTClaimsError = InvalidTokenError


def encode(payload: dict[str, Any], key: str, algorithm: str = "HS256") -> str:
    """签发 JWT，返回字符串。"""
    token = jwt.encode(payload, key, algorithm=algorithm)
    if isinstance(token, bytes):
        return token.decode("utf-8")
    return token


def decode(
    token: str,
    key: str | None,
    algorithms: Optional[Iterable[str]] = None,
    options: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """校验并解码 JWT。"""
    decode_options: dict[str, Any] = {"verify_aud": False}
    if options:
        decode_options.update(options)

    if decode_options.get("verify_signature") is False:
        return jwt.decode(
            token,
            options=decode_options,
        )

    return jwt.decode(
        token,
        key,
        algorithms=list(algorithms or ["HS256"]),
        options=decode_options,
    )


def _get_verification_key() -> str:
    """按当前配置返回 JWT 验签密钥（RS256 公钥或 HS256 密钥）。"""
    from app.core.config import settings
    from app.core.security import JWTUtils

    if settings.JWT_ALGORITHM == "RS256":
        return JWTUtils._load_rsa_key(
            settings.RSA_PUBLIC_KEY,
            settings.RSA_PUBLIC_KEY_PATH,
            "public",
        )
    return settings.SECRET_KEY


def decode_token_payload(token: str, *, verify_exp: bool = True) -> dict[str, Any]:
    """使用应用配置解码 access/refresh 令牌。"""
    from app.core.config import settings

    options: dict[str, Any] = {}
    if not verify_exp:
        options["verify_exp"] = False
    return decode(
        token.strip(),
        _get_verification_key(),
        algorithms=[settings.JWT_ALGORITHM],
        options=options or None,
    )


def decode_unsigned_payload(token: str) -> dict[str, Any]:
    """不验签解码（仅用于 CSRF 中间件提取 sub 等字段）。"""
    return decode(
        token,
        None,
        options={"verify_signature": False, "verify_exp": False},
    )


def resolve_access_token_from_request(request) -> Optional[str]:
    """从 Cookie 或 Authorization 头解析 access_token。"""
    cookie_token = request.cookies.get("access_token")
    if cookie_token and str(cookie_token).strip():
        return str(cookie_token).strip()

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer = auth_header[7:].strip()
        if bearer:
            return bearer
    return None


def extract_jti_from_request(request) -> Optional[str]:
    """从当前请求解析 access_token 的 jti（兼容 Cookie 与 Bearer）。"""
    token = resolve_access_token_from_request(request)
    if not token:
        return None
    try:
        payload = decode_token_payload(token, verify_exp=False)
        jti = payload.get("jti")
        return str(jti) if jti else None
    except Exception:
        return None
