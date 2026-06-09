"""外部对接 API 模块

职责：客户 API 密钥鉴权接口、Telegram Bot 管理接口。

权限：client_api 使用 MD5 签名；telegram 需管理员。

说明：对外开放接口，含客户 API（密钥+签名鉴权）与 Telegram 管理。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。"""
from .client_api import router as client_api_router
from .telegram import router as telegram_router

__all__ = ['client_api_router', 'telegram_router']
