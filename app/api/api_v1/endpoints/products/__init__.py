"""
产品管理模块
提供产品CRUD操作和分配历史
"""
from .products import router
from .assignments import router as assignments_router

__all__ = ['router', 'assignments_router']

