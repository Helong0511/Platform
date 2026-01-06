"""
API路由聚合模块
统一管理所有API端点的路由注册

优化说明：
- 按业务模块分组组织路由注册
- 使用清晰的注释标识每个模块
- 保持路由注册的逻辑顺序
"""
from fastapi import APIRouter

# 创建主API路由器
api_router = APIRouter()

# ==================== 导入所有端点模块 ====================
# 注意：导入顺序不影响功能，但建议按功能模块分组
from app.api.api_v1.endpoints import (
    # 认证模块
    auth,
    # 用户管理模块
    users,
    # 客户管理模块
    clients,
    # 产品管理模块
    products,
    product_assignments,
    # 广告数据模块
    ad_data,
    tb_search_data,
    # 仪表盘模块
    dashboard,
    # Excel处理模块
    excel,
    # ML模型模块
    ml_model,
    # 系统管理模块
    scheduled_tasks,
    audit_logs,
    sessions,
    notification_configs,
    # 外部接口模块
    client_api,
    telegram,
    # Postback模块
    postback,
    bft_postback,
    # 追踪模块
    tracking,
    short_links,
    # CPL系统模块
    advertisers,
    publishers,
    offers,
    caps,
    discounts,
    conversion_deductions,
    advertiser_tests,
    affiliate_tests,
    conversion_summary,
    conversion_log,
    clicks,
)

# ==================== 路由注册 ====================
# 按业务模块分组注册，便于管理和维护

# ---------- 认证模块 ----------
api_router.include_router(auth.router, prefix="/auth", tags=["认证管理"])

# ---------- 用户管理模块 ----------
api_router.include_router(users.router, prefix="/users", tags=["用户管理"])

# ---------- 客户管理模块 ----------
api_router.include_router(clients.router, prefix="/clients", tags=["客户管理"])

# ---------- 产品管理模块 ----------
api_router.include_router(products.router, prefix="/products", tags=["产品管理"])
api_router.include_router(product_assignments.router, prefix="/product-assignments", tags=["产品分配历史"])

# ---------- 广告数据模块 ----------
api_router.include_router(ad_data.router, prefix="/ad-data", tags=["广告数据"])
api_router.include_router(tb_search_data.router, prefix="/tb-search-data", tags=["TB搜索数据"])

# ---------- 仪表盘模块 ----------
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["仪表盘"])

# ---------- Excel处理模块 ----------
api_router.include_router(excel.router, prefix="/excel", tags=["Excel处理"])

# ---------- ML模型模块 ----------
api_router.include_router(ml_model.router, prefix="/ml-model", tags=["导入训练"])

# ---------- 系统管理模块 ----------
api_router.include_router(scheduled_tasks.router, prefix="/scheduled-tasks", tags=["定时任务管理"])
api_router.include_router(audit_logs.router, prefix="/audit-logs", tags=["操作日志"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["会话管理"])
api_router.include_router(notification_configs.router, prefix="/notification-configs", tags=["通知配置管理"])

# ---------- 外部接口模块 ----------
# 客户API路由（通过API密钥访问，无前缀）
api_router.include_router(client_api.router, prefix="", tags=["客户API"])
# Telegram Bot 管理路由
api_router.include_router(telegram.router, prefix="/telegram", tags=["Telegram Bot"])

# ---------- Postback模块 ----------
# BFT S2S PostBack 路由（外部回调接口，保留向后兼容，无前缀）
api_router.include_router(bft_postback.router, prefix="", tags=["BFT S2S"])
# 统一 Postback 服务路由（推荐使用，无前缀）
api_router.include_router(postback.router, prefix="", tags=["Postback服务"])

# ---------- 追踪模块 ----------
# 点击追踪路由（必须在其他路由之前，避免路径冲突，无前缀）
api_router.include_router(tracking.router, prefix="", tags=["点击追踪"])
# 短链接服务路由
api_router.include_router(short_links.router, prefix="/short-links", tags=["短链接服务"])

# ---------- CPL系统模块 ----------
api_router.include_router(advertisers.router, prefix="/advertisers", tags=["广告主管理"])
api_router.include_router(publishers.router, prefix="/publishers", tags=["渠道管理"])
api_router.include_router(offers.router, prefix="/offers", tags=["Offer管理"])
api_router.include_router(caps.router, prefix="/caps", tags=["Cap管理"])
api_router.include_router(discounts.router, prefix="/discounts", tags=["扣量管理"])
api_router.include_router(conversion_deductions.router, prefix="/conversion-deductions", tags=["转化扣减管理"])
api_router.include_router(advertiser_tests.router, prefix="/advertiser-tests", tags=["上游测试"])
api_router.include_router(affiliate_tests.router, prefix="/affiliate-tests", tags=["下游测试"])
api_router.include_router(conversion_summary.router, prefix="/conversion-summary", tags=["转化统计"])
api_router.include_router(conversion_log.router, prefix="/conversion-logs", tags=["转化日志"])
api_router.include_router(clicks.router, prefix="/clicks", tags=["短链接访问记录"])
