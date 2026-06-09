#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 frontend/src 中占位 JSDoc（/** fnName */）升级为详细简体中文说明。"""

import re
from pathlib import Path

ROOT = Path(r"e:/Platform/frontend/src")

# 函数名 -> 中文说明（优先精确匹配）
FN_DOCS = {
    "getPostbackConversions": "分页获取 Postback 转化记录列表。",
    "getPostbackStats": "获取 Postback 转化汇总统计。",
    "updateConversionStatus": "更新指定转化记录的处理状态。",
    "batchCreateIpWhitelist": "批量创建 Postback IP 白名单条目。",
    "getShortLinkDetail": "获取短链接详情（含关联 Offer/渠道等扩展字段）。",
    "getShortLinkStats": "获取短链接汇总统计（总数、激活数等）。",
    "checkShortCode": "校验短码是否已被占用。",
    "generateShortCode": "由服务端生成可用短码。",
    "getTBSearchDataList": "分页获取 TB 搜索数据列表（支持数据权限过滤）。",
    "getThirdPartyReportStats": "获取第三方上报记录汇总统计。",
    "getClientDetail": "获取客户（下游）详情，支持本地缓存。",
    "getAuditLogStats": "获取审计日志汇总统计（按日期范围）。",
    "getUserStats": "获取用户管理页汇总统计。",
    "getScheduledTasks": "分页获取定时任务列表。",
    "getScheduledTask": "获取单条定时任务详情。",
    "getUserSessions": "获取指定用户的活跃会话列表。",
    "getBlacklist": "获取会话黑名单列表。",
    "getProductDetail": "获取产品详情。",
    "getAvailableProductNames": "获取可分配的产品名称列表。",
    "getProductAssignments": "获取产品分配记录列表。",
    "getClientAssignments": "获取客户（下游）的产品分配情况。",
    "getNotificationRecords": "分页获取通知发送记录。",
    "getNotificationRecord": "获取单条通知记录详情。",
    "getAdminNotificationConfig": "获取管理员侧通知配置。",
    "getAdDataList": "分页获取广告数据列表。",
    "getDailySummary": "获取广告数据按日汇总。",
    "getProductById": "根据 ID 获取产品信息。",
    "getAdDataDateRange": "获取广告数据可用日期范围。",
    "getSourceTag": "根据上报来源返回 Element Plus 标签 type。",
    "getSourceLabel": "上报来源的中文展示名。",
    "getStatusTag": "上报状态对应的 Element Plus 标签 type。",
    "getStatusLabel": "上报状态的中文展示名。",
    "getResponseStatusTag": "HTTP 响应状态码对应的标签 type。",
    "formatReportJson": "将上报 JSON 格式化为缩进可读文本。",
    "getCurrentMonthRange": "返回当月首尾 ISO 时间字符串，供默认日期筛选。",
    "getStrategyLabel": "转化扣量策略的中文展示名。",
    "getCacheTypeColor": "缓存类型对应的标签颜色。",
    "getResourceTypeLabel": "审计日志资源类型的中文名。",
    "getActionTypeLabel": "审计日志操作类型的中文名。",
    "getStatusCodeTag": "HTTP 状态码对应的标签 type。",
    "getOsTagType": "操作系统类型对应的标签 type。",
    "getRowClientPublisherPO": "从表格行读取客户-渠道 PO 单价。",
    "getRowClientPublisherCap": "从表格行读取客户-渠道 Cap 上限。",
    "getRowClientPublisherTracklink": "从表格行读取客户-渠道 Tracklink。",
    "getClientPublisherPO": "获取客户-渠道 PO 单价（异步）。",
    "getClientPublisherCap": "获取客户-渠道 Cap 配置（异步）。",
    "getClientPublisherTracklinkSync": "同步获取客户-渠道 Tracklink。",
}

PREFIX_ZH = {
    "get": "获取",
    "create": "创建",
    "update": "更新",
    "delete": "删除",
    "export": "导出",
    "import": "导入",
    "batch": "批量",
    "check": "校验",
    "generate": "生成",
    "format": "格式化",
    "clear": "清除",
    "refresh": "刷新",
    "resolve": "解析",
    "ensure": "确认",
    "build": "构建",
    "load": "加载",
    "save": "保存",
    "reset": "重置",
    "handle": "处理",
    "fetch": "拉取",
    "send": "发送",
    "upload": "上传",
    "download": "下载",
}


def guess_doc(fn: str) -> str:
    if fn in FN_DOCS:
        return FN_DOCS[fn]
    for prefix, zh in PREFIX_ZH.items():
        if fn.startswith(prefix) and len(fn) > len(prefix):
            rest = fn[len(prefix):]
            # camelCase 拆分
            words = re.sub(r"([A-Z])", r" \1", rest).strip()
            return f"{zh}{words}。"
    return f"{fn} 接口。"


def upgrade_file(path: Path) -> bool:
    content = path.read_text(encoding="utf-8")
    original = content

    def repl(m):
        fn = m.group(1)
        doc = guess_doc(fn)
        return f"/**\n * {doc}\n */"

    content = re.sub(r"/\*\*\s*(\w+)\s*\*/", repl, content)

    if content != original:
        path.write_text(content, encoding="utf-8", newline="\n")
        return True
    return False


def before_ends_with_jsdoc(content: str, pos: int) -> bool:
    prefix = content[:pos].rstrip()
    return prefix.endswith("*/")


def main():
    changed = []
    for p in sorted(ROOT.rglob("*.js")):
        if upgrade_file(p):
            changed.append(p.relative_to(ROOT).as_posix())
    print(f"升级占位 JSDoc: {len(changed)} 个文件")
    for c in changed:
        print(c)


if __name__ == "__main__":
    main()
