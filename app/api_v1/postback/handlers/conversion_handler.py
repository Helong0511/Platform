"""
转化记录 API 适配层（委托 PostbackConversionService）。
"""
from app.services.cpl.postback_conversion_service import (
    ConversionHandler,
    PostbackConversionService,
    conversion_handler,
)

__all__ = [
    "ConversionHandler",
    "PostbackConversionService",
    "conversion_handler",
]
