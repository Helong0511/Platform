/** 审计日志展示与 JSON 格式化 */

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
    API_ACCESS: '',
    RUNTIME_ERROR: 'danger',
  };
  return tagMap[actionType] || '';
}

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
    API_ACCESS: 'API访问',
    RUNTIME_ERROR: '程序运行错误',
  };
  return labelMap[actionType] || actionType;
}

export function getStatusCodeTag(statusCode) {
  if (statusCode >= 200 && statusCode < 300) return 'success';
  if (statusCode >= 300 && statusCode < 400) return 'info';
  if (statusCode >= 400 && statusCode < 500) return 'warning';
  if (statusCode >= 500) return 'danger';
  return '';
}

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

    return JSON.stringify(formatValue(obj), null, 2);
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
      try {
        return JSON.stringify(JSON.parse(formatted), null, 2);
      } catch {
        return formatted;
      }
    }
    return String(jsonString);
  }
}
