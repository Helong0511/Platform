/**
 * 一次性脚本：为 frontend/src 下 .js/.vue 补充简体中文注释
 * 运行：node tests/frontend_add_comments.js
 */
import fs from 'fs';
import path from 'path';

const SRC = path.resolve('frontend/src');
const stats = { processed: [], skipped: [], failed: [] };

/** 路径 → 中文模块说明 */
const PATH_DESC = {
  'api/ad-data.js': '广告数据 API：列表查询、导出、筛选级联选项',
  'api/advertiser.js': '广告主（上游）管理 API：CRUD 与列表查询',
  'api/affiliate-test.js': '下游联调测试 API：模拟转化回传与结果查询',
  'api/app-config.js': '应用配置 API：全局开关与运行时参数',
  'api/audit-log.js': '审计日志 API：操作记录查询与导出',
  'api/auth.js': '认证 API：登录、登出、令牌刷新',
  'api/cache.js': '系统缓存管理 API：查看/删除 Redis 缓存条目',
  'api/cap.js': 'Cap 限额管理 API：上下游 Offer 流量上限配置',
  'api/clicks.js': '点击日志 API：短链接访问记录查询',
  'api/client.js': '客户（下游/渠道/商户）管理 API',
  'api/cloak-config.js': '斗篷（Cloak）配置 API：流量分流与伪装规则',
  'api/conversion-summary.js': '转化总览 API：按维度汇总转化数据',
  'api/dashboard.js': '仪表盘 API：统计卡片与趋势图数据',
  'api/deduction.js': '扣减日志 API：转化扣减执行记录',
  'api/discount.js': '扣量（折扣）配置 API',
  'api/ml-model.js': '机器学习模型管理 API',
  'api/notification.js': '通知配置 API：Telegram/产品/客户通知',
  'api/offer.js': 'Offer 管理 API：CRUD、状态与关联查询',
  'api/postback.js': 'Postback 回传管理 API',
  'api/product.js': '产品管理 API：产品与渠道分配',
  'api/publisher.js': '渠道（下游）管理 API',
  'api/scheduled-task.js': '定时任务 API：Cron 任务 CRUD 与手动触发',
  'api/sensitive-path-probes.js': '敏感路径探测 API：安全扫描配置',
  'api/session.js': '会话管理 API：在线用户会话查询与踢出',
  'api/short-link.js': '短链接管理 API',
  'api/tb-search-data.js': 'TB 搜索数据 API',
  'api/third-party-report.js': '第三方报表 API',
  'api/user.js': '用户管理 API：CRUD、密码、导出',
  'api/helpers/adDataSelectOptions.js': '广告数据筛选下拉选项辅助函数',
  'api/helpers/exportDownload.js': '列表导出下载辅助：处理 blob 响应',
  'api/helpers/notificationConfig.js': '通知配置表单辅助：字段映射与校验',
  'api/helpers/scheduledTaskPaths.js': '定时任务 API 路径常量',
  'api/helpers/withDataFilters.js': '请求参数注入数据筛选条件的包装器',
  'main.js': 'Vue 应用入口：注册插件、初始化 Axios/错误处理/版本检查',
  'router/index.js': 'Vue Router 配置：路由表、守卫与权限跳转',
  'store/index.js': 'Pinia 全局状态：认证信息与用户会话',
  'config/constants.js': '前端全局常量：角色、状态枚举与配置项',
  'services/telegram_notification_service.js': 'Telegram 通知服务封装',
};

/** composable 文件名 → 说明 */
function composableDesc(name) {
  const base = name.replace(/^use/, '').replace(/\.js$/, '');
  const map = {
    Pagination: '通用分页与筛选状态',
    OfferList: 'Offer 列表页：筛选、分页、数据加载',
    OfferForm: 'Offer 表单：创建/编辑校验与提交',
    OfferDetail: 'Offer 详情面板：关联数据展示',
    OfferColumnVisibility: 'Offer 表格列显隐持久化',
    UserList: '用户列表：搜索、分页与批量操作',
    UserForm: '用户表单：角色与权限字段',
    UserRowActions: '用户行操作：启用/禁用/重置密码',
    UserColumnVisibility: '用户表格列显隐',
    ClientForm: '客户表单：基本信息与 API 密钥',
    ClientProducts: '客户关联产品：分配与历史',
    ClientStats: '客户统计卡片数据',
    ClientApiDocExamples: '客户 API 文档示例代码生成',
    ClientUserManagementColumnVisibility: '客户用户管理列显隐',
    CacheList: '缓存列表：分页查询与筛选',
    CacheActions: '缓存操作：删除单条/批量清理',
    CapList: 'Cap 列表数据加载',
    CapForm: 'Cap 表单编辑',
    CapColumnVisibility: 'Cap 表格列显隐',
    ClickLogList: '点击日志列表查询',
    ClickLogColumnVisibility: '点击日志列显隐',
    ConversionSummary: '转化总览：维度筛选与汇总',
    ConversionSummaryColumnVisibility: '转化总览列显隐',
    ConversionDeductionList: '扣减配置列表',
    ConversionDeductionForm: '扣减配置表单',
    ConversionDeductionColumnVisibility: '扣减配置列显隐',
    DiscountList: '扣量配置列表',
    DiscountForm: '扣量配置表单',
    DiscountColumnVisibility: '扣量列显隐',
    DeductionLogsColumnVisibility: '扣减日志列显隐',
    PublisherList: '渠道列表数据',
    PublisherColumnVisibility: '渠道表格列显隐',
    PostbackConversions: 'Postback 转化记录查询',
    PostbackColumnVisibility: 'Postback 列显隐',
    PostbackIpWhitelistColumnVisibility: 'Postback IP 白名单列显隐',
    ShortLinkList: '短链接列表',
    ShortLinkForm: '短链接表单：占位符校验与预览',
    ShortLinkColumnVisibility: '短链接列显隐',
    ScheduledTasks: '定时任务列表与状态',
    ScheduledTaskActions: '定时任务操作：启停/立即执行',
    SessionManagementColumnVisibility: '会话管理列显隐',
    ThirdPartyReports: '第三方报表列表',
    ThirdPartyReportColumnVisibility: '第三方报表列显隐',
    AuditLogs: '审计日志列表查询',
    AuditLogColumnVisibility: '审计日志列显隐',
    AdvertiserManagementColumnVisibility: '广告主管理列显隐',
    AffiliateTestColumnVisibility: '下游测试列显隐',
    TbSearchTableFormat: 'TB 搜索表格字段格式化',
    TbSearchColumnVisibility: 'TB 搜索列显隐',
    TableColumnVisibility: '通用表格列显隐（localStorage 持久化）',
    AdDataFilterCascade: '广告数据筛选级联（上游→产品→Offer）',
    AdDataProductPanel: '广告数据产品面板状态',
    AdDataTableFormat: '广告数据表格字段格式化',
    AdDataColumnVisibility: '广告数据列显隐',
    DataPageFilterCascade: '数据页通用筛选级联',
    DebouncedPaginatedFetch: '防抖分页请求：避免频繁 API 调用',
    PageAuth: '页面级权限校验',
    MobileTouch: '移动端触摸交互优化',
    Device: '设备类型检测（移动/桌面）',
    CloakConfigs: '斗篷配置列表与表单状态',
  };
  return map[base] || `${base} 相关业务逻辑组合式函数`;
}

/** Vue 视图/组件 → 说明 */
function vueDesc(relPath) {
  const map = {
    'App.vue': '根组件：路由出口与浏览器扩展错误过滤',
    'views/Login.vue': '登录页：OAuth2 密码模式认证与跳转',
    'views/Dashboard.vue': '数据仪表盘：统计卡片与广告效果趋势图',
    'views/NotFound.vue': '404 页面：路由未匹配时的友好提示',
    'views/AdData.vue': '广告数据入口：子路由容器',
    'views/ApiDocumentation.vue': 'API 文档页：客户对接接口说明',
    'views/ad-data/DailyReport.vue': '广告数据 - 每日报表',
    'views/ad-data/TBSearchData.vue': '广告数据 - TB 搜索数据',
    'views/admin/AdvertiserManagement.vue': '管理端 - 广告主（上游）管理',
    'views/admin/AffiliateTest.vue': '管理端 - 下游联调测试',
    'views/admin/AuditLogManagement.vue': '管理端 - 审计日志',
    'views/admin/CacheManagement.vue': '管理端 - 系统缓存管理',
    'views/admin/CapManagement.vue': '管理端 - Cap 限额管理',
    'views/admin/ClickLog.vue': '管理端 - 短链接访问记录',
    'views/admin/CloakManagement.vue': '管理端 - 斗篷（Cloak）配置',
    'views/admin/ConversionDeductionManagement.vue': '管理端 - 转化扣减配置',
    'views/admin/ConversionSummary.vue': '管理端 - 转化总览',
    'views/admin/DeductionLogs.vue': '管理端 - 扣减执行日志',
    'views/admin/DeductionStats.vue': '管理端 - 扣减统计',
    'views/admin/DiscountManagement.vue': '管理端 - 扣量配置',
    'views/admin/MLModelManagement.vue': '管理端 - 机器学习模型',
    'views/admin/OfferManagement.vue': '管理端 - Offer 管理',
    'views/admin/PostbackIpWhitelist.vue': '管理端 - Postback IP 白名单',
    'views/admin/PostbackManagement.vue': '管理端 - Postback 回传管理',
    'views/admin/PublisherManagement.vue': '管理端 - 渠道（下游）管理',
    'views/admin/ScheduledTaskManagement.vue': '管理端 - 定时任务',
    'views/admin/SensitivePathProbeManagement.vue': '管理端 - 敏感路径探测',
    'views/admin/SessionManagement.vue': '管理端 - 在线会话管理',
    'views/admin/ShortLinkManagement.vue': '管理端 - 短链接管理',
    'views/admin/TelegramNotificationConfig.vue': '管理端 - Telegram 通知配置',
    'views/admin/ThirdPartyReportManagement.vue': '管理端 - 第三方报表',
    'views/admin/UserManagement.vue': '管理端 - 用户管理入口',
    'views/admin/user/UserList.vue': '管理端 - 用户列表',
    'views/admin/user/UserForm.vue': '管理端 - 用户表单（新建/编辑）',
    'views/admin/ad-data/AdDataList.vue': '管理端 - 广告数据明细列表',
    'views/client/ClientUserManagement.vue': '客户端 - 客户子用户管理',
    'components/Layout/MainLayout.vue': '主布局：顶栏、侧边栏与内容区',
    'components/Layout/Sidebar.vue': '侧边栏导航：按角色显示菜单项',
    'components/VirtualList.vue': '虚拟滚动列表：大数据量渲染优化',
    'components/VirtualTable.vue': '虚拟滚动表格：大数据量表格优化',
    'components/admin/FilterForm.vue': '通用筛选表单组件',
    'components/admin/StatsCards.vue': '统计卡片组：仪表盘指标展示',
    'components/admin/ClickLogFilter.vue': '点击日志筛选表单',
    'components/admin/ClickLogDetailDialog.vue': '点击日志详情弹窗',
    'components/admin/ShortLinkFormDialog.vue': '短链接创建/编辑弹窗',
    'components/admin/ShortLinkManagement.vue': '短链接管理内嵌组件',
    'components/admin/OfferStatsPanel.vue': 'Offer 统计面板',
    'components/admin/ClientNotificationConfigDialog.vue': '客户通知配置弹窗',
    'components/admin/ProductNotificationConfigDialog.vue': '产品通知配置弹窗',
    'components/admin/NotificationRecordsDialog.vue': '通知发送记录弹窗',
    'components/admin/ProductManagementDialog.vue': '产品管理弹窗',
    'components/admin/ProductAssignmentHistoryDialog.vue': '产品分配历史弹窗',
  };
  return map[relPath.replace(/\\/g, '/')] || `${relPath} 页面/组件`;
}

/** utils 文件名 → 说明 */
function utilDesc(name) {
  const map = {
    api: 'HTTP 请求封装：统一响应解析与错误处理',
    axiosConfig: 'Axios 实例配置：拦截器、CSRF、401 处理',
    authResponse: '认证响应解析：OAuth2 与用户信息提取',
    crudApi: 'CRUD API 工厂：生成标准增删改查方法',
    messages: '前后端统一消息常量与提取工具',
    logger: '前端日志工具：分级输出',
    date: '日期工具：格式化与区间计算',
    dateFormat: '日期显示格式化',
    uuid: 'UUID 生成工具',
    clipboard: '剪贴板复制工具',
    csrfToken: 'CSRF 令牌读取',
    csrfMutate: '变更请求 CSRF 刷新',
    userClient: '用户-客户关联判断工具',
    domFixes: 'DOM 兼容性修复（如下拉框显示）',
    errorFilter: '错误消息过滤：忽略扩展/无关错误',
    globalErrorHandler: '全局 JS 错误捕获与审计上报',
    versionCheck: '生产环境前端版本检查与自动刷新',
    cacheFormat: '缓存条目展示格式化',
    currencyFormat: '金额格式化',
    percentFormat: '百分比格式化',
    postbackFormat: 'Postback 数据格式化',
    conversionSummaryFormat: '转化总览字段格式化',
    conversionDeductionFormat: '扣减配置字段格式化',
    conversionDeductionFormRules: '扣减配置表单校验规则',
    thirdPartyReportFormat: '第三方报表字段格式化',
    auditLogFormat: '审计日志字段格式化',
    adDataRequest: '广告数据请求参数构建',
    cachedDetailFetch: '带缓存的详情请求',
    clientApiSignature: '客户 API 签名生成',
    offerTracklink: 'Offer 追踪链接处理',
    shortLinkFormRules: '短链接表单校验规则',
    shortLinkPlaceholderValidate: '短链接占位符校验',
    discountFormRules: '扣量表单校验规则',
    capFormRules: 'Cap 表单校验规则',
    cronValidate: 'Cron 表达式校验',
    cloakReportEvents: '斗篷上报事件工具',
  };
  const base = name.replace(/\.js$/, '');
  return map[base] || `${base} 工具函数`;
}

function walk(dir, acc = []) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    if (fs.statSync(p).isDirectory()) walk(p, acc);
    else if (/\.(js|vue)$/.test(f)) acc.push(p);
  }
  return acc;
}

function hasChineseFileHeader(content, ext) {
  const head = content.trimStart().slice(0, 1200);
  if (ext === '.vue') {
    const m = head.match(/^<!--([\s\S]*?)-->/);
    if (m && /[\u4e00-\u9fff]{8,}/.test(m[1])) return true;
    return false;
  }
  const m = head.match(/^\/\*\*([\s\S]*?)\*\//);
  if (m && /[\u4e00-\u9fff]{8,}/.test(m[1])) return true;
  return false;
}

function getFileDesc(relPath, ext) {
  const norm = relPath.replace(/\\/g, '/');
  if (PATH_DESC[norm]) return PATH_DESC[norm];
  if (norm.startsWith('composables/')) {
    return `组合式函数 - ${composableDesc(path.basename(norm))}`;
  }
  if (norm.startsWith('utils/')) {
    return `工具模块 - ${utilDesc(path.basename(norm))}`;
  }
  if (ext === '.vue') return vueDesc(norm);
  return norm;
}

function makeJsHeader(desc, relPath) {
  return `/**
 * ${desc}
 * @file ${relPath.replace(/\\/g, '/')}
 */\n`;
}

function makeVueHeader(desc, relPath) {
  return `<!--\n  ${desc}\n  @file ${relPath.replace(/\\/g, '/')}\n-->\n`;
}

/** 为 composable 主函数补充 JSDoc */
function enhanceComposable(content, desc) {
  let changed = false;
  const fnMatch = content.match(/export\s+function\s+(use\w+)\s*\(/);
  if (!fnMatch) return { content, changed };

  const fnName = fnMatch[1];
  const idx = content.indexOf(fnMatch[0]);
  const before = content.slice(0, idx);
  if (/\/\*\*[\s\S]*?@returns/.test(before.slice(-600))) return { content, changed };

  const doc = `/**
 * ${desc}
 * @returns {Object} 响应式状态与业务操作方法
 */\n`;
  content = before + doc + content.slice(idx);
  changed = true;
  return { content, changed };
}

/** 为无 JSDoc 的 export function 补充简要说明 */
function enhanceExportFunctions(content) {
  let changed = false;
  const re = /(^|\n)(export\s+(?:async\s+)?function\s+(\w+)\s*\([^)]*\)\s*\{)/g;
  let m;
  const inserts = [];
  while ((m = re.exec(content)) !== null) {
    const start = m.index + m[1].length;
    const before = content.slice(Math.max(0, start - 300), start);
    if (/\/\*\*[\s\S]*?\*\//.test(before)) continue;
    inserts.push({ pos: start, name: m[3] });
  }
  for (let i = inserts.length - 1; i >= 0; i--) {
    const { pos, name } = inserts[i];
    const doc = `/** ${name} */\n`;
    content = content.slice(0, pos) + doc + content.slice(pos);
    changed = true;
  }
  return { content, changed };
}

/** 为 export const fn = 补充 JSDoc */
function enhanceExportConsts(content) {
  let changed = false;
  const re = /(^|\n)(export\s+const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)/g;
  let m;
  const inserts = [];
  while ((m = re.exec(content)) !== null) {
    const start = m.index + m[1].length;
    const before = content.slice(Math.max(0, start - 300), start);
    if (/\/\*\*[\s\S]*?\*\//.test(before)) continue;
    inserts.push({ pos: start, name: m[3] });
  }
  for (let i = inserts.length - 1; i >= 0; i--) {
    const { pos, name } = inserts[i];
    content = content.slice(0, pos) + `/** ${name} */\n` + content.slice(pos);
    changed = true;
  }
  return { content, changed };
}

/** Vue template 主要区块注释 */
const TEMPLATE_MARKERS = [
  { re: /<template>/, insert: '<template>\n  <!-- 页面主模板 -->' },
  { re: /<el-dialog([^>]*)>/, comment: '<!-- 弹窗：表单/详情 -->', once: true },
  { re: /<el-table([^>]*)>/, comment: '<!-- 数据表格 -->', once: true },
  { re: /<el-form([^>]*)>/, comment: '<!-- 筛选/编辑表单 -->', once: true },
  { re: /<el-pagination/, comment: '<!-- 分页器 -->', once: true },
  { re: /class="[^"]*filter/, comment: '<!-- 筛选区域 -->', once: true },
];

function enhanceVueTemplate(content) {
  let changed = false;
  const tplMatch = content.match(/<template>([\s\S]*?)<\/template>/);
  if (!tplMatch) return { content, changed };

  let tpl = tplMatch[1];
  const originalTpl = tpl;

  if (!/<!--[\s\S]*?页面|模板|主|筛选|表格|弹窗/.test(tpl.slice(0, 200))) {
    tpl = tpl.replace(/^\s*/, (ws) => `${ws}<!-- 页面主模板 -->\n`);
    changed = true;
  }

  const markers = [
    { re: /<el-dialog\b/, c: '<!-- 弹窗区域 -->' },
    { re: /<el-table\b/, c: '<!-- 数据表格 -->' },
    { re: /<el-form\b/, c: '<!-- 表单区域 -->' },
    { re: /<el-pagination\b/, c: '<!-- 分页 -->' },
    { re: /class="[^"]*toolbar/, c: '<!-- 工具栏 -->' },
    { re: /class="[^"]*filter/, c: '<!-- 筛选区 -->' },
  ];

  for (const { re, c } of markers) {
    const m = tpl.match(re);
    if (m && !tpl.includes(c)) {
      const idx = m.index;
      const lineStart = tpl.lastIndexOf('\n', idx) + 1;
      const indent = tpl.slice(lineStart, idx).match(/^(\s*)/)[1];
      tpl = tpl.slice(0, lineStart) + `${indent}${c}\n` + tpl.slice(lineStart);
      changed = true;
    }
  }

  if (changed) {
    content = content.replace(/<template>[\s\S]*?<\/template>/, `<template>${tpl}</template>`);
  }
  return { content, changed };
}

function processFile(filePath) {
  const rel = path.relative(SRC, filePath);
  const ext = path.extname(filePath);
  let content = fs.readFileSync(filePath, 'utf8');
  const original = content;
  let changed = false;
  const desc = getFileDesc(rel, ext);

  try {
    if (!hasChineseFileHeader(content, ext)) {
      const header = ext === '.vue' ? makeVueHeader(desc, rel) : makeJsHeader(desc, rel);
      content = header + content;
      changed = true;
    }

    if (ext === '.js') {
      if (rel.replace(/\\/g, '/').startsWith('composables/')) {
        const r = enhanceComposable(content, desc);
        content = r.content;
        changed = changed || r.changed;
      }
      if (rel.replace(/\\/g, '/').startsWith('api/')) {
        const r1 = enhanceExportFunctions(content);
        const r2 = enhanceExportConsts(content);
        content = r2.content;
        changed = changed || r1.changed || r2.changed;
      }
      if (rel.replace(/\\/g, '/').startsWith('utils/')) {
        const r = enhanceExportFunctions(content);
        content = r.content;
        changed = changed || r.changed;
      }
    }

    if (ext === '.vue') {
      const r = enhanceVueTemplate(content);
      content = r.content;
      changed = changed || r.changed;
    }

    if (content !== original) {
      fs.writeFileSync(filePath, content, 'utf8');
      stats.processed.push(rel);
    } else {
      stats.skipped.push(rel);
    }
  } catch (e) {
    stats.failed.push({ rel, error: e.message });
  }
}

const files = walk(SRC).sort();
for (const f of files) processFile(f);

console.log(JSON.stringify({
  total: files.length,
  processed: stats.processed.length,
  skipped: stats.skipped.length,
  failed: stats.failed.length,
  processedFiles: stats.processed,
  skippedFiles: stats.skipped,
  failedFiles: stats.failed,
}, null, 2));
