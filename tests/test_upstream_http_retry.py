"""上游 HTTP 超时重试"""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.scheduler_module import upstream_http as uh


@pytest.mark.asyncio
async def test_post_json_retries_on_timeout_then_succeeds():
    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.json.return_value = {"access_token": "tok"}

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("read timed out"),
            ok_response,
        ]
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch.object(uh, "_default_max_retries", return_value=2), patch(
        "app.scheduler_module.upstream_http.httpx.AsyncClient", return_value=mock_client
    ), patch.object(uh.asyncio, "sleep", new_callable=AsyncMock):
        data = await uh.post_json(
            "https://example.com/token",
            json_body={"u": "a"},
            label="Test API",
            timeout=20.0,
            max_retries=2,
        )

    assert data["access_token"] == "tok"
    assert mock_client.request.await_count == 2


@pytest.mark.asyncio
async def test_post_json_raises_after_all_retries():
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=httpx.ReadTimeout("read timed out"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.scheduler_module.upstream_http.httpx.AsyncClient", return_value=mock_client
    ), patch.object(uh.asyncio, "sleep", new_callable=AsyncMock):
        with pytest.raises(Exception, match="已重试 2 次"):
            await uh.post_json(
                "https://example.com/token",
                label="Test API",
                timeout=20.0,
                max_retries=2,
            )
