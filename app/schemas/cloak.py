"""
斗篷配置相关 Schema
"""
import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

# ---------------------------------------------------------------------------
# Meta Pixel / Conversions API 官方「标准事件」event_name（与 Meta 文档 Standard Events 一致）。
# 文档：https://developers.facebook.com/docs/meta-pixel/reference
# 说明：无名为「点击查看」的标准事件；内容/落地互动常用 ViewContent；按钮类可用自定义名如 Click。
# ---------------------------------------------------------------------------
FACEBOOK_STANDARD_EVENT_NAMES = frozenset(
    {
        "AddPaymentInfo",  # 填写支付信息
        "AddToCart",  # 加入购物车
        "AddToWishlist",  # 加入心愿单
        "CompleteRegistration",  # 完成注册
        "Contact",  # 发起联系
        "CustomizeProduct",  # 定制商品
        "Donate",  # 捐赠
        "FindLocation",  # 查找线下位置
        "InitiateCheckout",  # 发起结账
        "Lead",  # 潜在客户/销售线索
        "PageView",  # 页面浏览（浏览器像素常自动上报；CAPI 亦可显式发送）
        "Purchase",  # 购买（须配合 value + currency）
        "Schedule",  # 预约
        "Search",  # 搜索
        "StartTrial",  # 开始试用
        "SubmitApplication",  # 提交申请
        "Subscribe",  # 订阅（如付费订阅）
        "ViewContent",  # 查看内容/关键页浏览
    }
)

# 非标准事件名：须字母开头，仅字母/数字/下划线，总长 2～64（与 DB String(64) 一致），将作为 Meta 自定义事件上报。
_CLOAK_REPORT_EVENT_CUSTOM_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,62}$")


def validate_cloak_report_event_name(value: str) -> str:
    """
    校验斗篷桥页点击上报使用的 CAPI event_name。
    - 官方标准事件：见 FACEBOOK_STANDARD_EVENT_NAMES
    - 自定义事件：如 Click、CloakButtonClick（需在广告管理工具中配置自定义转化或作受众信号时使用）
    """
    value = (value or "").strip() or "ViewContent"
    if value in FACEBOOK_STANDARD_EVENT_NAMES:
        return value
    if _CLOAK_REPORT_EVENT_CUSTOM_RE.fullmatch(value):
        return value
    raise ValueError(
        f"不支持的上报事件：{value!r}。"
        "请从 Meta 官方标准事件名中选择，或使用自定义事件名（字母开头，仅含字母、数字、下划线，2～64 字符）。"
    )


# 兼容旧引用：等同于官方标准集合（自定义事件以 validate_cloak_report_event_name 为准）
ALLOWED_CLOAK_REPORT_EVENTS = FACEBOOK_STANDARD_EVENT_NAMES


class CloakConfigBase(BaseModel):
    """斗篷配置基础模型"""
    cloak_name: str = Field(..., min_length=1, max_length=100, description="斗篷名称（如 master）")
    pixel_id: str = Field(..., min_length=1, max_length=50, description="主像素ID")
    access_token: str = Field(..., min_length=1, max_length=500, description="主像素Token")
    backup_pixel_id: Optional[str] = Field(None, max_length=50, description="备份像素ID")
    backup_access_token: Optional[str] = Field(None, max_length=500, description="备份像素Token")
    report_event: str = Field(
        "ViewContent",
        max_length=64,
        description="桥页按钮点击跳转时 CAPI 的 event_name（须 click_report_enabled 为真才实际上报）",
    )
    report_value: Optional[float] = Field(
        None,
        ge=0,
        description="点击上报为 Purchase 时的金额（必填）",
    )
    report_currency: Optional[str] = Field(
        "USD",
        max_length=10,
        description="点击上报为 Purchase 时的货币（ISO 4217）",
    )
    click_report_enabled: bool = Field(
        True,
        description="是否启用「按钮点击跳转」Facebook 上报（事件与金额为上方 report_*）",
    )
    load_report_enabled: bool = Field(
        False,
        description="是否启用「桥页加载完成」Facebook 上报",
    )
    load_report_event: str = Field(
        "PageView",
        max_length=64,
        description="加载完成时的 CAPI event_name",
    )
    load_report_value: Optional[float] = Field(None, ge=0, description="加载上报为 Purchase 时的金额")
    load_report_currency: Optional[str] = Field(
        "USD",
        max_length=10,
        description="加载上报为 Purchase 时的货币",
    )
    postback_report_enabled: bool = Field(
        False,
        description="postback 收到转化时是否按本配置上报；关闭则保持系统原行为（按 payout 发 Purchase）",
    )
    postback_report_event: str = Field(
        "Purchase",
        max_length=64,
        description="postback 转化时的 CAPI event_name（依赖点击记录 url_params 含 dp=斗篷名）",
    )
    postback_report_value: Optional[float] = Field(
        None,
        ge=0,
        description="postback 为 Purchase 时的固定金额；不填则在处理器中用 postback 的 payout",
    )
    postback_report_currency: Optional[str] = Field(
        "USD",
        max_length=10,
        description="postback Purchase 货币",
    )
    is_enabled: bool = Field(True, description="是否启用")

    @field_validator("report_event")
    @classmethod
    def validate_report_event(cls, value: str) -> str:
        return validate_cloak_report_event_name(value)

    @field_validator("load_report_event")
    @classmethod
    def validate_load_report_event(cls, value: str) -> str:
        return validate_cloak_report_event_name(value)

    @field_validator("postback_report_event")
    @classmethod
    def validate_postback_report_event(cls, value: str) -> str:
        return validate_cloak_report_event_name(value)

    @field_validator("report_currency", "load_report_currency", "postback_report_currency")
    @classmethod
    def validate_currencies(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return "USD"
        v = value.strip().upper()
        return v or "USD"

    @model_validator(mode="after")
    def cloak_report_phase_consistency(self):
        if self.report_event == "Purchase":
            if self.report_value is None:
                raise ValueError("点击上报事件为 Purchase 时必须填写金额（report_value）")
        if self.load_report_enabled and self.load_report_event == "Purchase":
            if self.load_report_value is None:
                raise ValueError("启用加载上报且事件为 Purchase 时必须填写 load_report_value")
        return self

    @field_validator("cloak_name")
    @classmethod
    def validate_cloak_name(cls, value: str) -> str:
        value = value.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", value):
            raise ValueError("斗篷名称仅支持字母、数字、下划线和中划线")
        return value

    @field_validator("pixel_id")
    @classmethod
    def validate_pixel_id(cls, value: str) -> str:
        value = value.strip()
        if not value.isdigit():
            raise ValueError("像素ID必须为数字")
        return value

    @field_validator("backup_pixel_id")
    @classmethod
    def validate_backup_pixel_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if value == "":
            return None
        if not value.isdigit():
            raise ValueError("备份像素ID必须为数字")
        return value

    @field_validator("access_token", "backup_access_token")
    @classmethod
    def trim_tokens(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class CloakConfigCreate(CloakConfigBase):
    """创建斗篷配置"""
    pass


class CloakConfigUpdate(BaseModel):
    """更新斗篷配置"""
    cloak_name: Optional[str] = Field(None, min_length=1, max_length=100, description="斗篷名称（如 master）")
    pixel_id: Optional[str] = Field(None, min_length=1, max_length=50, description="主像素ID")
    access_token: Optional[str] = Field(None, min_length=1, max_length=500, description="主像素Token")
    backup_pixel_id: Optional[str] = Field(None, max_length=50, description="备份像素ID")
    backup_access_token: Optional[str] = Field(None, max_length=500, description="备份像素Token")
    report_event: Optional[str] = Field(None, max_length=64, description="点击跳转上报事件名")
    report_value: Optional[float] = Field(None, ge=0, description="点击上报 Purchase 金额")
    report_currency: Optional[str] = Field(None, max_length=10, description="点击上报 Purchase 货币")
    click_report_enabled: Optional[bool] = Field(None, description="是否启用点击跳转 Facebook 上报")
    load_report_enabled: Optional[bool] = Field(None, description="是否启用加载完成 Facebook 上报")
    load_report_event: Optional[str] = Field(None, max_length=64, description="加载完成上报事件名")
    load_report_value: Optional[float] = Field(None, ge=0, description="加载上报 Purchase 金额")
    load_report_currency: Optional[str] = Field(None, max_length=10, description="加载上报 Purchase 货币")
    postback_report_enabled: Optional[bool] = Field(None, description="是否按本配置做 postback Facebook 上报")
    postback_report_event: Optional[str] = Field(None, max_length=64, description="postback 上报事件名")
    postback_report_value: Optional[float] = Field(None, ge=0, description="postback Purchase 固定金额，可空")
    postback_report_currency: Optional[str] = Field(None, max_length=10, description="postback Purchase 货币")
    is_enabled: Optional[bool] = Field(None, description="是否启用")

    @field_validator("report_event")
    @classmethod
    def validate_report_event(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return validate_cloak_report_event_name(value)

    @field_validator("load_report_event")
    @classmethod
    def validate_load_report_event(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return validate_cloak_report_event_name(value)

    @field_validator("postback_report_event")
    @classmethod
    def validate_postback_report_event(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return validate_cloak_report_event_name(value)

    @field_validator("report_currency", "load_report_currency", "postback_report_currency")
    @classmethod
    def validate_currencies_update(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip().upper()
        return v or None

    @field_validator("cloak_name")
    @classmethod
    def validate_cloak_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", value):
            raise ValueError("斗篷名称仅支持字母、数字、下划线和中划线")
        return value

    @field_validator("pixel_id")
    @classmethod
    def validate_pixel_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value.isdigit():
            raise ValueError("像素ID必须为数字")
        return value

    @field_validator("backup_pixel_id")
    @classmethod
    def validate_backup_pixel_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if value == "":
            return None
        if not value.isdigit():
            raise ValueError("备份像素ID必须为数字")
        return value

    @field_validator("access_token", "backup_access_token")
    @classmethod
    def trim_tokens(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class CloakConfigResponse(CloakConfigBase):
    """斗篷配置响应"""
    id: int
    created_at: datetime
    updated_at: datetime
    bridge_html_present: bool = Field(
        False,
        description="是否已在磁盘部署桥页 HTML（任一路径存在 {cloak_name}.html）",
    )
    is_usable: bool = Field(
        False,
        description="斗篷是否可用：已检测到对应桥页 HTML 则为可用，否则不可用（无法启用对外使用）",
    )

    model_config = ConfigDict(from_attributes=True)


class TestCloakReportRequest(BaseModel):
    """测试上报请求（事件名与金额按 report_phase 取自斗篷配置对应阶段）"""
    report_phase: Literal["load", "click", "postback"] = Field(
        "click",
        description="测试上报阶段：load=加载完成（载），click=点击跳转（点），postback=转化（转）",
    )
    adsid: str = Field("test-fbclid-123456", min_length=1, max_length=500, description="测试广告事件ID")
    email: str = Field("test@example.com", min_length=1, max_length=255, description="测试邮箱")
    phone: str = Field("13800138000", min_length=1, max_length=50, description="测试手机号")
    ip: str = Field("127.0.0.1", min_length=1, max_length=50, description="测试IP地址")
    ua: str = Field("Mozilla/5.0", min_length=1, description="测试UA")
    use_hash: bool = Field(True, description="是否使用哈希")
