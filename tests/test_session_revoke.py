"""会话令牌撤销与刷新轮换单元测试。"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.session_service import (
    TokenReuseError,
    collect_tokens_from_request,
    revoke_tokens_from_request,
)


class _FakeRequest:
    def __init__(self, cookies=None, authorization=None):
        self.cookies = cookies or {}
        self.headers = {}
        if authorization:
            self.headers["Authorization"] = authorization


def test_collect_tokens_from_cookie_and_bearer():
    request = _FakeRequest(
        cookies={"access_token": "cookie-access", "refresh_token": "cookie-refresh"},
        authorization="Bearer header-access",
    )
    tokens = collect_tokens_from_request(request, extra_tokens=["body-refresh"])
    assert tokens == ["cookie-access", "cookie-refresh", "header-access", "body-refresh"]


@pytest.mark.asyncio
async def test_revoke_tokens_blacklists_bearer_access():
    db = AsyncMock()
    db.execute.return_value = MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
    request = _FakeRequest(authorization="Bearer access-jwt-token")

    payload = {"jti": "jti-access", "exp": 9999999999}
    with patch(
        "app.services.session_service._blacklist_single_token",
        new_callable=AsyncMock,
    ) as mock_blacklist:
        await revoke_tokens_from_request(
            db=db,
            request=request,
            user_id=1,
            reason="用户退出登录",
        )
    mock_blacklist.assert_called_once()
    assert mock_blacklist.call_args[0][2] == "access-jwt-token"


@pytest.mark.asyncio
async def test_consume_refresh_token_raises_on_reuse():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=IntegrityError("insert", {}, Exception()))
    db.rollback = AsyncMock()

    with patch(
        "app.core.jwt_codec.decode_token_payload",
        return_value={"jti": "refresh-jti", "exp": 9999999999},
    ):
        db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        )
        from app.services.session_service import _blacklist_single_token

        with pytest.raises(TokenReuseError):
            await _blacklist_single_token(
                db,
                1,
                "refresh-token-value",
                "刷新令牌轮换",
                require_fresh=True,
                flush_immediately=True,
            )
