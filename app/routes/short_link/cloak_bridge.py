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
import stat

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


def resolve_bridge_static_path(filename: str, search_bases: tuple[str, ...]) -> str | None:
    """只解析白名单扩展名的普通静态文件，拒绝路径穿越、符号链接和特殊文件。"""
    if (
        not isinstance(filename, str)
        or not re.fullmatch(r"[a-zA-Z0-9_-][a-zA-Z0-9_.-]*", filename)
        or filename in {".", ".."}
    ):
        return None
    _, extension = os.path.splitext(filename)
    if extension.lower() not in _CONTENT_TYPE_MAP:
        return None

    for base in search_bases:
        candidate = os.path.join(base, filename)
        try:
            candidate_stat = os.lstat(candidate)
        except FileNotFoundError:
            continue
        # 静态资源目录不允许用符号链接暴露目录外文件。
        if stat.S_ISREG(candidate_stat.st_mode) and not stat.S_ISLNK(candidate_stat.st_mode):
            return candidate
    return None


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
        # 生产环境静态资源目录（与 cloak_scripts_paths 中 SCRIPTS_DIR_SERVER 同级 bridge 子目录）
        scripts_dir_server = "/data/Platform/scripts/bridge"
        # 本地开发：app/routes/short_link -> app -> 项目根 -> scripts/bridge
        current_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        scripts_dir_local = os.path.join(current_dir, "scripts", "bridge")

        file_path = resolve_bridge_static_path(
            filename, (scripts_dir_server, scripts_dir_local)
        )
        if not file_path:
            logger.warning("[桥页静态资源] 文件名非法、文件类型不允许或文件不存在：%s", filename)
            raise_short_link_not_found("文件不存在")

        _, ext = os.path.splitext(filename)
        content_type = _CONTENT_TYPE_MAP[ext.lower()]

        response = FileResponse(file_path, media_type=content_type)
        response.headers["Content-Security-Policy"] = _BRIDGE_STATIC_CSP
        # 静态资源内容不变，可浏览器/CDN 缓存 7 天
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
