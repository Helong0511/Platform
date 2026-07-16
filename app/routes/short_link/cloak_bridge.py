"""
桥页静态资源路由模块。

斗篷桥页 HTML（如 master.html）中常引用相对路径的图片、CSS、JS 等资源。
本模块通过 GET /bridge/{filename} 对外提供这些文件，查找路径与桥页 HTML 一致：
优先服务器目录 /data/Platform/scripts/bridge，其次项目根 scripts/bridge。

安全要点：
- 文件名白名单校验，禁止 ../ 等路径穿越
- 响应附带 CSP 头，限制脚本与资源来源
- 静态资源可长期缓存（7 天），与桥页 HTML 的 no-cache 策略区分
"""
import logging
import os
import re

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.routes.short_link.errors import raise_short_link_not_found

logger = logging.getLogger(__name__)

# 允许通过 URL 访问的静态资源扩展名 → MIME 类型映射
_CONTENT_TYPE_MAP = {
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

# 桥页静态资源与 HTML 共用 CSP 策略，允许 cdnjs 字体/样式
_BRIDGE_STATIC_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; "
    "script-src-attr 'none'; object-src 'none'; "
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
    "img-src 'self' data: https: blob:; font-src 'self' data: "
    "https://cdnjs.cloudflare.com; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
    "upgrade-insecure-requests"
)


def register_bridge_routes(router: APIRouter) -> None:
    """
    将 /bridge/{filename} 静态资源路由注册到短链接路由器。

    由 short_link 主路由模块在启动时调用，与 /change、/report 等斗篷路由一并挂载。
    """

    @router.get(
        "/bridge/{filename}",
        summary="服务桥页静态资源（图片、CSS、JS 等）",
        tags=["短链接服务"],
    )
    async def serve_bridge_static(filename: str, request: Request = None):
        """
        按文件名返回桥页引用的静态资源。

        Args:
            filename: 资源文件名（不含路径），如 logo.png、style.css
            request: FastAPI 请求对象（当前未使用，保留供后续审计/限流扩展）

        Returns:
            FileResponse：磁盘文件流，附带 CSP 与缓存头

        Raises:
            HTTPException 404：文件名非法或文件不存在（统一返回「文件不存在」避免泄露目录结构）
        """
        # 白名单：仅字母、数字、点、下划线、连字符，防止 ../../../etc/passwd 类攻击
        if not re.match(r"^[a-zA-Z0-9_.-]+$", filename):
            logger.warning("[桥页静态资源] 文件名包含非法字符：%s", filename)
            raise_short_link_not_found("文件不存在")

        # 生产环境静态资源目录（与 cloak_scripts_paths 中 SCRIPTS_DIR_SERVER 同级 bridge 子目录）
        scripts_dir_server = "/data/Platform/scripts/bridge"
        # 本地开发：app/routes/short_link -> app -> 项目根 -> scripts/bridge
        current_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        scripts_dir_local = os.path.join(current_dir, "scripts", "bridge")

        file_path_server = os.path.join(scripts_dir_server, filename)
        file_path_local = os.path.join(scripts_dir_local, filename)

        # 服务器路径优先，与桥页 HTML 读取策略一致
        file_path = None
        if os.path.exists(file_path_server) and os.path.isfile(file_path_server):
            file_path = file_path_server
        elif os.path.exists(file_path_local) and os.path.isfile(file_path_local):
            file_path = file_path_local
        else:
            logger.warning("[桥页静态资源] 文件不存在：%s", filename)
            raise_short_link_not_found("文件不存在")

        # 按扩展名设置 Content-Type；未知扩展名用 application/octet-stream
        _, ext = os.path.splitext(filename)
        content_type = _CONTENT_TYPE_MAP.get(ext.lower(), "application/octet-stream")

        response = FileResponse(file_path, media_type=content_type)
        response.headers["Content-Security-Policy"] = _BRIDGE_STATIC_CSP
        # 静态资源内容不变，可浏览器/CDN 缓存 7 天
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
