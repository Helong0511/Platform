"""转化记录 API 适配层。

将 PostbackConversionService 及其 Handler 实例重新导出，
供管理端查询、筛选、导出转化记录时注入路由依赖。
实际查询与权限过滤逻辑在 app.services.cpl.postback_conversion_service 中实现。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
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
