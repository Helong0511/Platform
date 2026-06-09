"""
广告数据服务 — 统一导出入口（兼容层）。

功能说明：
- 对外暴露 ``AdDataService`` 与 ``join_country_info_for_ad_data``，避免调用方感知子包结构
- 实际实现位于 ``app.services.ad_data.service`` 及 queries/calculators 子模块

在系统中的位置：
- 被广告数据相关 API 与管理端报表引用

注意事项：
1. 新功能应实现在 ``app.services.ad_data`` 子包，本文件仅做 re-export
2. 勿在本文件添加业务逻辑，保持薄导出层
"""
from app.services.ad_data.service import AdDataService, join_country_info_for_ad_data

__all__ = ["AdDataService", "join_country_info_for_ad_data"]
