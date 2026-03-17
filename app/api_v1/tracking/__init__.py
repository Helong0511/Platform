"""
追踪模块
提供点击追踪和短链接功能
"""
from .tracking import router
from .short_links import router as short_links_router

__all__ = ['router', 'short_links_router']

