"""桥页静态资源路由。"""
import logging
import os
import re

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)


def register_bridge_routes(router: APIRouter) -> None:
    @router.get(
        "/bridge/{filename}",
        summary="服务桥页静态资源（图片、CSS、JS 等）",
        tags=["短链接服务"],
    )
    async def serve_bridge_static(filename: str, request: Request = None):
        if not re.match(r"^[a-zA-Z0-9_.-]+$", filename):
            logger.warning("[桥页静态资源] 文件名包含非法字符：%s", filename)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件不存在",
            )

        scripts_dir_server = "/data/Platform/scripts/bridge"
        current_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        scripts_dir_local = os.path.join(current_dir, "scripts", "bridge")

        file_path_server = os.path.join(scripts_dir_server, filename)
        file_path_local = os.path.join(scripts_dir_local, filename)

        file_path = None
        if os.path.exists(file_path_server) and os.path.isfile(file_path_server):
            file_path = file_path_server
        elif os.path.exists(file_path_local) and os.path.isfile(file_path_local):
            file_path = file_path_local
        else:
            logger.warning("[桥页静态资源] 文件不存在：%s", filename)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件不存在",
            )

        content_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
            ".css": "text/css",
            ".js": "application/javascript",
            ".json": "application/json",
            ".html": "text/html",
        }
        _, ext = os.path.splitext(filename)
        content_type = content_type_map.get(ext.lower(), "application/octet-stream")

        response = FileResponse(file_path, media_type=content_type)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "img-src 'self' data: https: blob:; font-src 'self' data: "
            "https://cdnjs.cloudflare.com; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
            "upgrade-insecure-requests"
        )
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
