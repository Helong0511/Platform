"""
短链接重定向 — 向后兼容导入层。

功能说明：
- 历史代码可能 ``from app.routes.short_link_redirect import router``，本模块保留该路径
- 实际实现已迁至 ``app.routes.short_link`` 包，此处仅做再导出，无业务逻辑

导出符号：
- ``router``：FastAPI 路由实例（/s/{short_code} 等）
- ``create_click_record`` / ``_create_click_record``：点击记录异步写入入口

注意事项：
1. 新代码应直接 ``from app.routes.short_link import router``
2. 勿在本文件新增逻辑，避免与 ``short_link`` 包产生双份实现
"""
from app.routes.short_link import router
from app.routes.short_link.utils import create_click_record

_create_click_record = create_click_record

__all__ = ["router", "create_click_record", "_create_click_record"]
