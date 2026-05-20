"""
短链接重定向 — 向后兼容层。

实现已迁至 app.routes.short_link 包；本模块仅保留历史导入路径。
"""
from app.routes.short_link import router
from app.routes.short_link.utils import create_click_record

_create_click_record = create_click_record

__all__ = ["router", "create_click_record", "_create_click_record"]
