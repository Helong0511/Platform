/**
 * 工具模块 - 审计日志字段格式化
 * @file utils/auditLogFormat.js
 */
export function getActionTypeTag(actionType) {
  const tagMap = {
    LOGIN: 'success',
    LOGOUT: 'info',
    CREATE: 'success',
    UPDATE: 'warning',
    DELETE: 'danger',
    IMPORT: 'success',
    EXPORT: 'info',
    ACTIVATE: 'success',
    DEACTIVATE: 'warning',
    TASK_RUN: 'primary',
    CLEANUP: 'warning',
    API_ACCESS: '',
    RUNTIME_ERROR: 'danger',
    REVOKE_SESSION: 'warning',
    REVOKE_ALL_SESSIONS: 'warning',
    CSRF_VIOLATION: 'danger',
  };
  return tagMap[actionType] || '';
}

/**
 * 审计日志资源类型的中文名。
 */
export function getResourceTypeLabel(resourceType) {
  const labelMap = {
    USER: '用户',
    CLIENT: '客户',
    PRODUCT: '产品',
    AD_DATA: '广告数据',
    SCHEDULED_TASK: '定时任务',
    FILE_LOGS: '文件日志',
    SYSTEM: '系统',
    FRONTEND: '前端',
    SESSION: '会话',
    OFFER: 'Offer',
    PUBLISHER: '渠道',
    ADVERTISER: '广告主',
    CONVERSION_DEDUCTION_CONFIG: '转化扣减配置',
    CLOAK_CONFIG: '斗篷配置',
    NOTIFICATION_CONFIG: '通知配置',
    SHORT_LINK: '短链接',
    OFFER_CAP: 'Cap配置',
    OFFER_DISCOUNT: '扣量配置',
    SENSITIVE_BLOCKED_IP: '敏感路径黑名单IP',
    SENSITIVE_PATH_PROBE_LOG: '敏感路径拦截日志',
    THIRD_PARTY_REPORT_LOG: '第三方上报日志',
    TB_SEARCH_DATA: 'TB搜索数据',
    POSTBACK_FORWARD_LOG: 'Postback转发日志',
    POSTBACK_CONVERSION: 'Postback转化',
    POSTBACK_PENDING_CONVERSION: 'Postback待确认转化',
    POSTBACK_IP_WHITELIST: 'Postback IP白名单',
    PRODUCT_ASSIGNMENT: '产品分配',
    AFFILIATE_TEST: '下游测试',
    TELEGRAM: 'Telegram',
    CLICK: '点击记录',
  };
  return labelMap[resourceType] || resourceType;
}

/**
 * 审计日志操作类型的中文名。
 */
export function getActionTypeLabel(actionType) {
  const labelMap = {
    LOGIN: '登录',
    LOGOUT: '登出',
    CREATE: '增加',
    UPDATE: '修改',
    DELETE: '删除',
    IMPORT: '导入',
    EXPORT: '导出',
    ACTIVATE: '激活',
    DEACTIVATE: '禁用',
    TASK_RUN: '定时任务运行',
    CLEANUP: '清理',
    API_ACCESS: 'API访问',
    RUNTIME_ERROR: '程序运行错误',
    REVOKE_SESSION: '撤销会话',
    REVOKE_ALL_SESSIONS: '撤销全部会话',
    CSRF_VIOLATION: 'CSRF违规',
  };
  return labelMap[actionType] || actionType;
}

/**
 * HTTP 状态码对应的标签 type。
 */
export function getStatusCodeTag(statusCode) {
  if (statusCode >= 200 && statusCode < 300) return 'success';
  if (statusCode >= 300 && statusCode < 400) return 'info';
  if (statusCode >= 400 && statusCode < 500) return 'warning';
  if (statusCode >= 500) return 'danger';
  return '';
}

import { formatJson as formatJsonBase } from './jsonFormat';

/**
 * 格式化Audit Json（含日期字段简化）。
 */
export function formatAuditJson(jsonString) {
  try {
    let obj = typeof jsonString === 'string' ? JSON.parse(jsonString) : jsonString;

    const formatValue = (value) => {
      if (value === null || value === undefined) return value;
      if (typeof value === 'string') {
        const dateMatch = value.match(/^(\d{4}-\d{2}-\d{2})(T\d{2}:\d{2}:\d{2})?/);
        if (dateMatch) return dateMatch[1];
        const pythonDateMatch = value.match(/datetime\.date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)/);
        if (pythonDateMatch) {
          const year = pythonDateMatch[1];
          const month = String(pythonDateMatch[2]).padStart(2, '0');
          const day = String(pythonDateMatch[3]).padStart(2, '0');
          return `${year}-${month}-${day}`;
        }
      }
      if (Array.isArray(value)) return value.map(formatValue);
      if (typeof value === 'object') {
        const formatted = {};
        for (const [key, val] of Object.entries(value)) {
          formatted[key] = formatValue(val);
        }
        return formatted;
      }
      return value;
    };

    return formatJsonBase(formatValue(obj));
  } catch {
    if (typeof jsonString === 'string') {
      let formatted = jsonString.replace(
        /datetime\.date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)/g,
        (_match, year, month, day) => {
          const monthStr = String(month).padStart(2, '0');
          const dayStr = String(day).padStart(2, '0');
          return `"${year}-${monthStr}-${dayStr}"`;
        },
      );
      formatted = formatted.replace(/'/g, '"');
      return formatJsonBase(formatted, formatted);
    }
    return formatJsonBase(jsonString, String(jsonString ?? ''));
  }
}
