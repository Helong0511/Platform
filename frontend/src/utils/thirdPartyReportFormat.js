export function getSourceTag(source) {
  const tagMap = {
    short_link: 'primary',
    postback: 'success',
    unknown: 'info',
  };
  return tagMap[source] || '';
}

export function getSourceLabel(source) {
  const labelMap = {
    short_link: '短链接',
    postback: 'Postback',
    unknown: '其他',
  };
  return labelMap[source] || source;
}

export function getStatusTag(status) {
  const tagMap = {
    success: 'success',
    failed: 'danger',
    pending: 'warning',
  };
  return tagMap[status] || '';
}

export function getStatusLabel(status) {
  const labelMap = {
    success: '成功',
    failed: '失败',
    pending: '处理中',
  };
  return labelMap[status] || status;
}

export function getResponseStatusTag(statusCode) {
  if (statusCode >= 200 && statusCode < 300) return 'success';
  if (statusCode >= 300 && statusCode < 400) return 'info';
  if (statusCode >= 400 && statusCode < 500) return 'warning';
  if (statusCode >= 500) return 'danger';
  return '';
}

export function formatReportJson(jsonString) {
  try {
    const obj = typeof jsonString === 'string' ? JSON.parse(jsonString) : jsonString;
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(jsonString);
  }
}

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
