"""
广告数据服务 — 统一导出入口。

实现位于 ``app.services.ad_data.service``。
"""
from app.services.ad_data.service import AdDataService, join_country_info_for_ad_data

__all__ = ["AdDataService", "join_country_info_for_ad_data"]
