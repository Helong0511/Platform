/**
 * 第三方上报页展示格式化工具
 *
 * 职责：来源/状态标签、HTTP 状态色、JSON 美化、当月默认时间范围。
 * @file utils/thirdPartyReportFormat.js
 */
/** 根据上报来源返回 Element Plus 标签 type */
export function getSourceTag(source) {
  const tagMap = {
    short_link: 'primary',
    postback: 'success',
    unknown: 'info',
  };
  return tagMap[source] || '';
}

/** 上报来源的中文展示名 */
export function getSourceLabel(source) {
  const labelMap = {
    short_link: '短链接',
    postback: 'Postback',
    unknown: '其他',
  };
  return labelMap[source] || source;
}

/**
 * 上报状态对应的 Element Plus 标签 type。
 */
export function getStatusTag(status) {
  const tagMap = {
    success: 'success',
    failed: 'danger',
    pending: 'warning',
  };
  return tagMap[status] || '';
}

/**
 * 上报状态的中文展示名。
 */
export function getStatusLabel(status) {
  const labelMap = {
    success: '成功',
    failed: '失败',
    pending: '处理中',
  };
  return labelMap[status] || status;
}

/**
 * HTTP 响应状态码对应的标签 type。
 */
export function getResponseStatusTag(statusCode) {
  if (statusCode >= 200 && statusCode < 300) return 'success';
  if (statusCode >= 300 && statusCode < 400) return 'info';
  if (statusCode >= 400 && statusCode < 500) return 'warning';
  if (statusCode >= 500) return 'danger';
  return '';
}

/**
 * 将上报 JSON 格式化为缩进可读文本。
 */
export function formatReportJson(jsonString) {
  try {
    const obj = typeof jsonString === 'string' ? JSON.parse(jsonString) : jsonString;
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(jsonString);
  }
}

/**
 * 返回当月首尾 ISO 时间字符串，供默认日期筛选。
 */
export function getCurrentMonthRange() {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const startDate = new Date(year, month, 1, 0, 0, 0);
  const lastDay = new Date(year, month + 1, 0, 23, 59, 59);
  const fmt = (date) => {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    const h = String(date.getHours()).padStart(2, '0');
    const min = String(date.getMinutes()).padStart(2, '0');
    const s = String(date.getSeconds()).padStart(2, '0');
    return `${y}-${m}-${d}T${h}:${min}:${s}`;
  };
  return [fmt(startDate), fmt(lastDay)];
}
