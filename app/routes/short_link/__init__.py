"""
短链接重定向模块
导出路由供主应用使用

模块结构：
- router.py: 路由定义
- handlers.py: 请求处理逻辑
- placeholder.py: 占位符替换服务
- url_builder.py: URL构建服务
- utils.py: 工具函数
"""
from app.routes.short_link.router import router

__all__ = ["router"]

