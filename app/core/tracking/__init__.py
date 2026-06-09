"""
点击追踪模块（app/core/tracking）。

负责 click_id 生成、追踪令牌编解码、Tracklink/Postback URL 拼装，
供短链跳转、Postback 归因与点击落库链路使用。
"""
from app.core.tracking.click_id_generator import (
    generate_click_id,
    generate_unique_click_id,
    generate_click_id_from_timestamp,
    generate_click_id_unified,
)
from app.core.tracking.click_token import (
    use_tracking_token,
    generate_tracking_click_id,
    resolve_click_from_token,
    build_tracking_user_params,
)
from app.core.tracking.ad_tracking_codec import AdTrackingCodec
from app.core.tracking.tracklink_generator import (
    generate_upstream_tracklink,
    generate_downstream_tracklink,
    generate_postback_url
)

__all__ = [
    "generate_click_id",
    "generate_unique_click_id",
    "generate_click_id_from_timestamp",
    "generate_click_id_unified",
    "use_tracking_token",
    "generate_tracking_click_id",
    "resolve_click_from_token",
    "build_tracking_user_params",
    "AdTrackingCodec",
    "generate_upstream_tracklink",
    "generate_downstream_tracklink",
    "generate_postback_url",
]

