#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 frontend/src 下 .js/.vue 文件批量补充简体中文注释（仅追加，不改逻辑）。"""

import os
import re
from pathlib import Path

ROOT = Path(r"e:/Platform/frontend/src")
STATS = {"processed": [], "skipped": [], "failed": []}

# 文件名 -> 模块/组件职责说明
DESCRIPTIONS = {
    "useCapColumnVisibility.js": "Cap 管理页表格列显示偏好 composable，基于 useTableColumnVisibility 持久化到 localStorage。",
    "useAdvertiserManagementColumnVisibility.js": "广告主管理页表格列显示偏好 composable。",
    "useAffiliateTestColumnVisibility.js": "联盟测试页表格列显示偏好 composable。",
    "useAuditLogColumnVisibility.js": "审计日志页表格列显示偏好 composable。",
    "useClickLogColumnVisibility.js": "点击日志页表格列显示偏好 composable。",
    "useClientUserManagementColumnVisibility.js": "客户用户管理页表格列显示偏好 composable。",
    "useConversionDeductionColumnVisibility.js": "转化扣量管理页表格列显示偏好 composable。",
    "useConversionSummaryColumnVisibility.js": "转化总览页表格列显示偏好 composable。",
    "useDeductionLogsColumnVisibility.js": "扣量日志页表格列显示偏好 composable。",
    "useDiscountColumnVisibility.js": "扣量配置页表格列显示偏好 composable。",
    "useOfferColumnVisibility.js": "Offer 管理页表格列显示偏好 composable。",
    "usePostbackColumnVisibility.js": "Postback 管理页表格列显示偏好 composable。",
    "usePostbackIpWhitelistColumnVisibility.js": "Postback IP 白名单页表格列显示偏好 composable。",
    "usePublisherColumnVisibility.js": "渠道管理页表格列显示偏好 composable。",
    "useSessionManagementColumnVisibility.js": "会话管理页表格列显示偏好 composable。",
    "useShortLinkColumnVisibility.js": "短链接管理页表格列显示偏好 composable。",
    "useTbSearchColumnVisibility.js": "TB 搜索数据页表格列显示偏好 composable。",
    "useThirdPartyReportColumnVisibility.js": "第三方上报页表格列显示偏好 composable。",
    "useUserColumnVisibility.js": "用户管理页表格列显示偏好 composable。",
    "usePagination.js": "通用分页与筛选 composable，封装页码、每页条数及筛选表单重置。",
    "useTableColumnVisibility.js": "表格列显示偏好通用 composable，支持 localStorage 持久化与固定列。",
    "useAuditLogs.js": "审计日志列表 composable：筛选、分页、统计与详情弹窗。",
    "useCacheActions.js": "缓存管理页操作 composable：清理、刷新等。",
    "useCacheList.js": "缓存管理列表 composable：分页加载与筛选。",
    "useCapForm.js": "Cap 配置表单 composable：校验、提交与编辑态。",
    "useCapList.js": "Cap 配置列表 composable：筛选、分页与 CRUD 联动。",
    "useClickLogList.js": "短链接访问记录（Click Log）列表 composable：筛选、详情与 Facebook 补报。",
    "useClientApiDocExamples.js": "客户 API 文档示例 composable，生成请求示例与签名说明。",
    "useClientForm.js": "客户（下游）表单 composable：创建/编辑校验与提交。",
    "useClientProducts.js": "客户关联产品 composable：分配、撤销与历史记录。",
    "useClientStats.js": "客户侧统计 composable：仪表盘指标加载。",
    "useConversionDeductionForm.js": "转化扣量配置表单 composable。",
    "useConversionDeductionList.js": "转化扣量配置列表 composable。",
    "useConversionSummary.js": "转化总览 composable：汇总数据、筛选与导出。",
    "useDiscountForm.js": "扣量（Discount）配置表单 composable。",
    "useDiscountList.js": "扣量配置列表 composable。",
    "useOfferDetail.js": "Offer 详情 composable：加载详情与 Tracklink 展示。",
    "useOfferForm.js": "Offer 表单 composable：创建/编辑与校验。",
    "useOfferList.js": "Offer 列表 composable：筛选、分页与状态切换。",
    "usePostbackConversions.js": "Postback 转化记录 composable。",
    "usePublisherList.js": "渠道（Publisher）列表 composable。",
    "useScheduledTaskActions.js": "定时任务操作 composable：启停、立即执行等。",
    "useScheduledTasks.js": "定时任务列表 composable：分页与筛选。",
    "useShortLinkForm.js": "短链接表单 composable：占位符校验与提交。",
    "useShortLinkList.js": "短链接列表 composable：筛选、分页与批量操作。",
    "useThirdPartyReports.js": "第三方上报记录 composable。",
    "useUserForm.js": "用户表单 composable：角色、客户关联与权限字段。",
    "useUserList.js": "用户列表 composable：筛选、分页与行操作。",
    "useUserRowActions.js": "用户行操作 composable：编辑、禁用、删除等。",
    "conversionSummaryFormat.js": "转化总览页格式化工具：日期范围、汇总行、CSV 导出。",
    "thirdPartyReportFormat.js": "第三方上报页格式化工具：来源/状态标签、JSON 展示、当月时间范围。",
    "userClient.js": "用户与客户（下游）关联解析工具：从用户行解析 client_id。",
    "uuid.js": "UUID 生成工具，优先 crypto.randomUUID，旧环境回退 Math.random。",
    "MainLayout.vue": "应用主布局：桌面侧边栏、移动端抽屉菜单、顶栏用户信息与登出。",
    "Sidebar.vue": "侧边导航菜单：按角色展示路由项，支持移动端点击后关闭抽屉。",
    "FilterForm.vue": "通用筛选表单组件：公司名称、状态、日期范围，v-model 双向绑定。",
    "StatsCards.vue": "统计卡片组组件：展示关键指标与趋势。",
    "ClickLogFilter.vue": "点击日志筛选栏组件。",
    "ClickLogDetailDialog.vue": "点击日志详情弹窗组件。",
    "ClientNotificationConfigDialog.vue": "客户通知配置弹窗。",
    "NotificationRecordsDialog.vue": "通知发送记录弹窗。",
    "OfferStatsPanel.vue": "Offer 统计面板组件。",
    "ProductAssignmentHistoryDialog.vue": "产品分配历史弹窗。",
    "ProductManagementDialog.vue": "产品管理弹窗。",
    "ProductNotificationConfigDialog.vue": "产品通知配置弹窗。",
    "ShortLinkFormDialog.vue": "短链接创建/编辑弹窗。",
    "ShortLinkManagement.vue": "短链接管理内嵌组件（表格与操作）。",
    "Dashboard.vue": "仪表盘页面：广告效果趋势图与核心统计卡片。",
    "AdData.vue": "广告数据入口页面，承载子路由。",
    "ApiDocumentation.vue": "客户 API 对接文档页面。",
    "NotFound.vue": "404 未找到页面。",
    "DailyReport.vue": "广告数据日报页面。",
    "TBSearchData.vue": "TB 搜索数据报表页面。",
    "AdvertiserManagement.vue": "广告主（上游）管理页面。",
    "AffiliateTest.vue": "联盟链接测试页面。",
    "AuditLogManagement.vue": "审计日志管理页面。",
    "CacheManagement.vue": "系统缓存管理页面。",
    "CapManagement.vue": "Cap 上限配置管理页面。",
    "ClickLog.vue": "短链接访问记录（Click Log）页面。",
    "ConversionDeductionManagement.vue": "转化扣量规则管理页面。",
    "ConversionSummary.vue": "转化总览报表页面。",
    "DeductionLogs.vue": "扣量执行日志页面。",
    "DeductionStats.vue": "扣量统计页面。",
    "DiscountManagement.vue": "扣量（Discount）配置管理页面。",
    "MLModelManagement.vue": "机器学习模型管理页面。",
    "OfferManagement.vue": "Offer 管理页面。",
    "PostbackIpWhitelist.vue": "Postback IP 白名单管理页面。",
    "PublisherManagement.vue": "渠道（下游）管理页面。",
    "ScheduledTaskManagement.vue": "定时任务管理页面。",
    "SensitivePathProbeManagement.vue": "敏感路径探测管理页面。",
    "SessionManagement.vue": "用户会话管理页面。",
    "ShortLinkManagement.vue": "短链接管理页面。",
    "TelegramNotificationConfig.vue": "Telegram 通知配置页面。",
    "ThirdPartyReportManagement.vue": "第三方上报记录管理页面。",
    "UserManagement.vue": "用户管理入口页面。",
    "ClientUserManagement.vue": "客户侧用户管理页面。",
}


def has_good_file_header(content: str, is_vue: bool) -> bool:
    """判断是否已有完善的中文文件头。"""
    if is_vue:
        m = re.match(r"^<!--([\s\S]*?)-->", content.strip())
    else:
        m = re.match(r"^/\*\*([\s\S]*?)\*/", content.strip())
    if not m:
        return False
    text = m.group(1)
    chinese = re.findall(r"[\u4e00-\u9fff]", text)
    return len(chinese) >= 8 and len(text.strip()) >= 12


def guess_description(path: Path) -> str:
    name = path.name
    if name in DESCRIPTIONS:
        return DESCRIPTIONS[name]
    stem = path.stem
    if stem.startswith("use") and stem.endswith("ColumnVisibility"):
        page = stem.replace("use", "").replace("ColumnVisibility", "")
        return f"{page} 管理页表格列显示偏好 composable。"
    if stem.startswith("use"):
        return f"{stem} 组合式函数模块。"
    if path.suffix == ".vue":
        return f"{stem} 页面/组件。"
    return f"{stem} 工具模块。"


def make_js_header(desc: str) -> str:
    return f"/**\n * {desc}\n */\n"


def make_vue_header(desc: str) -> str:
    return f"<!-- {desc} -->\n"


def add_export_jsdoc(content: str, fn_name: str, desc: str) -> str:
    pattern = rf"(?<!\*/\n)(?<!\n \* .*\n)(export function {re.escape(fn_name)}\()"
    if re.search(rf"/\*\*[\s\S]*?\*/\s*\nexport function {re.escape(fn_name)}\(", content):
        return content
    jsdoc = f"/**\n * {desc}\n * @returns {{Object}} composable 暴露的状态与方法\n */\n"
    return re.sub(pattern, jsdoc + rf"export function {fn_name}(", content, count=1)


def add_fn_jsdoc_before(content: str, fn_pattern: str, jsdoc: str) -> str:
    """在 export function 前加 JSDoc（若尚无）。"""
    pat = rf"export function ({fn_pattern})\("
    for m in re.finditer(pat, content):
        start = m.start()
        prefix = content[:start].rstrip()
        if prefix.endswith("*/"):
            continue
        name = m.group(1)
        doc = jsdoc.replace("{name}", name)
        content = content[:start] + doc + content[start:]
        break
    return content


def enhance_third_party_report_format(content: str) -> str:
    if has_good_file_header(content, False):
        return content
    header = make_js_header("第三方上报页展示格式化：来源/状态标签、HTTP 状态色、JSON 美化、当月 ISO 时间范围。")
    content = header + content
    func_docs = {
        "getSourceTag": "根据上报来源返回 Element Plus 标签 type。",
        "getSourceLabel": "上报来源中文展示名。",
        "getStatusTag": "上报状态对应的标签 type。",
        "getStatusLabel": "上报状态中文展示名。",
        "getResponseStatusTag": "HTTP 响应状态码对应的标签 type。",
        "formatReportJson": "将上报 JSON 字符串格式化为缩进可读文本。",
        "getCurrentMonthRange": "返回当月首尾时刻的 ISO 字符串数组，供日期筛选默认值。",
    }
    for fn, doc in func_docs.items():
        content = add_export_jsdoc(content.replace(f"export function {fn}", f"export function {fn}", 1), fn, doc) if f"export function {fn}" in content else content
        # fix double - use simpler approach
    for fn, doc in func_docs.items():
        pat = rf"(?<!\*/\n)(export function {fn}\()"
        if re.search(rf"/\*\*[\s\S]*?\*/\s*\nexport function {fn}\(", content):
            continue
        jsdoc = f"/**\n * {doc}\n */\n"
        content = re.sub(pat, jsdoc + rf"export function {fn}(", content, count=1)
    return content


def enhance_conversion_summary_format(content: str) -> str:
    if has_good_file_header(content, False):
        return content
    header = make_js_header("转化总览页格式化工具：默认月份范围、客户侧转化展示、表格汇总行、CSV 导出。")
    return header + content


def enhance_user_client(content: str) -> str:
    if has_good_file_header(content, False):
        return content
    header = make_js_header("用户与客户（下游）关联解析：从列表行补全 client_id，供 API 文档与产品分配使用。")
    content = header + content
    for fn, doc in [
        ("resolveClientIdForUser", "解析用户行中的客户 ID；缺失时拉取详情并回写 user.client。"),
        ("ensureUserHasClient", "确认客户角色用户已关联客户实体，否则提示并返回 false。"),
    ]:
        pat = rf"(?<!\*/\n)(export async function {fn}\()"
        if not re.search(rf"/\*\*[\s\S]*?\*/\s*\nexport async function {fn}\(", content):
            jsdoc = f"/**\n * {doc}\n * @param {{Object}} user 用户行数据\n * @returns {('Promise<number|null>' if 'resolve' in fn else 'Promise<boolean>')}\n */\n"
            content = re.sub(pat, jsdoc + rf"export async function {fn}(", content, count=1)
    return content


def add_vue_template_section_comments(content: str) -> str:
    """为 Vue template 主要区块补充 HTML 注释（若缺失）。"""
    if "<template>" not in content:
        return content
    replacements = [
        (r"(<template>\s*\n\s*<div[^>]*>)", r"<template>\n  <!-- 页面根容器 -->\n  \1".replace(r"\1", r"\1"), None),
    ]
    # 在 template 开头加页面容器注释
    if "<!-- 页面根容器 -->" not in content and "<!-- 页面" not in content[:500]:
        content = re.sub(
            r"(<template>\s*\n)(\s*<div)",
            r"\1  <!-- 页面根容器 -->\n\2",
            content,
            count=1,
        )
    # 常见区块
    markers = [
        (r'(<template #header>)', "<!-- 卡片标题栏 -->", "card-header"),
        (r'(<el-dialog)', "<!-- 弹窗 -->", "el-dialog-comment"),
        (r'(class="search-bar")', "<!-- 筛选/搜索栏 -->", "search-bar"),
        (r'(<el-table\s)', "<!-- 数据表格 -->", "data-table"),
        (r'(<el-pagination)', "<!-- 分页 -->", "pagination"),
        (r'(<el-form[^>]*ref="form")', "<!-- 表单 -->", "form-ref"),
    ]
    for pattern, comment, key in markers:
        if comment in content:
            continue
        if re.search(pattern, content):
            content = re.sub(pattern, comment + r"\n      \1" if "search-bar" in key else comment + r"\n    \1", content, count=1)
            break
    return content


def process_file(path: Path) -> None:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    try:
        original = path.read_text(encoding="utf-8")
    except Exception as e:
        STATS["failed"].append((rel, str(e)))
        return

    is_vue = path.suffix == ".vue"
    content = original
    changed = False

    # 特殊文件增强
    if path.name == "thirdPartyReportFormat.js":
        new_content = enhance_third_party_report_format(content)
        if new_content != content:
            content, changed = new_content, True
    elif path.name == "conversionSummaryFormat.js":
        new_content = enhance_conversion_summary_format(content)
        if new_content != content:
            content, changed = new_content, True
    elif path.name == "userClient.js":
        new_content = enhance_user_client(content)
        if new_content != content:
            content, changed = new_content, True

    # 文件头
    if not has_good_file_header(content, is_vue):
        desc = guess_description(path)
        header = make_vue_header(desc) if is_vue else make_js_header(desc)
        content = header + content.lstrip("\ufeff")
        changed = True

    # composable 导出 JSDoc
    if path.parent.name == "composables" and "export function use" in content:
        m = re.search(r"export function (use\w+)\(", content)
        if m:
            fn = m.group(1)
            desc = guess_description(path).rstrip("。")
            new_c = add_export_jsdoc(content, fn, desc)
            if new_c != content:
                content = new_c
                changed = True

    # Vue template 区块注释
    if is_vue:
        new_c = add_vue_template_section_comments(content)
        if new_c != content:
            content = new_c
            changed = True

    # usePagination 文件头（函数内已有 JSDoc，补文件头即可）— 已在文件头逻辑覆盖

    if changed:
        path.write_text(content, encoding="utf-8", newline="\n")
        STATS["processed"].append(rel)
    else:
        STATS["skipped"].append(rel)


def main():
    files = sorted(ROOT.rglob("*"))
    targets = [p for p in files if p.suffix in (".js", ".vue")]
    for p in targets:
        process_file(p)
    print(f"总计: {len(targets)}")
    print(f"已处理: {len(STATS['processed'])}")
    print(f"已跳过: {len(STATS['skipped'])}")
    print(f"失败: {len(STATS['failed'])}")
    if STATS["processed"]:
        print("\n--- 已处理 ---")
        for x in STATS["processed"]:
            print(x)
    if STATS["skipped"]:
        print("\n--- 已跳过 ---")
        for x in STATS["skipped"]:
            print(x)
    if STATS["failed"]:
        print("\n--- 失败 ---")
        for x, e in STATS["failed"]:
            print(x, e)


if __name__ == "__main__":
    main()
