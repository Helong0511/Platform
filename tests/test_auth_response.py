"""认证成功响应包装单测"""
import json

from app.core.auth_response import build_token_json_response


def test_build_token_json_response_shape():
    response = build_token_json_response(
        access_token="access-abc",
        refresh_token="refresh-xyz",
        user={"id": 1, "username": "admin"},
        message="登录成功",
    )
    body = json.loads(response.body.decode())
    assert body["code"] == 200
    assert body["data"]["access_token"] == "access-abc"
    assert body["data"]["refresh_token"] == "refresh-xyz"
    assert body["data"]["user"]["username"] == "admin"
    assert response.headers.get("set-cookie")
