"""敏感路径防护中间件单测"""
import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from httpx import ASGITransport, AsyncClient

from app.core.middleware import SensitivePathGuardMiddleware


async def _home(_request):
    return PlainTextResponse("ok")


@pytest.fixture
def guarded_app():
    app = Starlette(routes=[Route("/", _home)])
    app.add_middleware(SensitivePathGuardMiddleware)
    return app


@pytest.mark.asyncio
async def test_blocks_env_probe(guarded_app):
    transport = ASGITransport(app=guarded_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/.env")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_allows_normal_path(guarded_app):
    transport = ASGITransport(app=guarded_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.text == "ok"
