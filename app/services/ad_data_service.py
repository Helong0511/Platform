"""
广告数据服务 — 统一导出入口。

实现位于 ``app.services.ad_data.service``（原 monolith 已迁入包内）。
未完成的拆分草稿见 ``ad_data_service_stub.py``，勿用于生产 API。
"""
from app.services.ad_data.service import AdDataService, join_country_info_for_ad_data

__all__ = ["AdDataService", "join_country_info_for_ad_data"]
