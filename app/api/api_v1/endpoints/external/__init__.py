"""
外部接口模块
提供外部系统调用的API接口
"""
from .client_api import router as client_api_router
from .telegram import router as telegram_router

__all__ = ['client_api_router', 'telegram_router']

