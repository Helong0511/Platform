"""
短链接重定向子包。

功能说明：
- 提供公开短链接入口 ``/s/{short_code}``，完成缓存/查库、占位符替换、点击归因与 302 跳转
- 挂载斗篷（Cloak）子路由：change、report、bridge 等，与桥页 HTML 及像素上报联动

模块结构：
- ``router.py``：路由注册与请求分发（薄路由层）
- ``handlers.py``：缓存命中 / 数据库查询两种重定向处理流程
- ``placeholder.py``：原始 URL 与查询参数中的占位符替换
- ``url_builder.py``：最终跳转 URL 的参数合并与构建
- ``utils.py``：Offer/渠道解析、点击记录创建等工具函数
- ``cloak_*``：斗篷变更、上报、桥页、点击持久化等子模块

在系统中的位置：
- 由 ``app.main`` 挂载；依赖 ``app.core.short_link_cache``、``app.core.tracking`` 等核心模块

注意事项：
1. 短链接路由通常不限流，改动需评估高并发影响
2. 占位符替换失败时应移除含未替换占位符的查询参数，避免上游收到无效 URL
"""
from app.routes.short_link.router import router

__all__ = ["router"]
