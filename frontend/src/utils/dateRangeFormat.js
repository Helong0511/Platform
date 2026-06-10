/**
 * 日期范围工具
 * @file utils/dateRangeFormat.js
 */

/**
 * 返回当月首尾日期。
 * @param {'date'|'iso'} [format='date'] - date: YYYY-MM-DD；iso: 带时间的 ISO 字符串
 * @returns {[string, string]}
 */
export function getMonthDateRange(format = 'date') {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const start = new Date(year, month, 1);
  const end =
    format === 'iso'
      ? new Date(year, month + 1, 0, 23, 59, 59)
      : new Date(year, month + 1, 0);

  if (format === 'iso') {
    const fmt = (date) => {
      const y = date.getFullYear();
      const m = String(date.getMonth() + 1).padStart(2, '0');
      const d = String(date.getDate()).padStart(2, '0');
      const h = String(date.getHours()).padStart(2, '0');
      const min = String(date.getMinutes()).padStart(2, '0');
      const s = String(date.getSeconds()).padStart(2, '0');
      return `${y}-${m}-${d}T${h}:${min}:${s}`;
    };
    return [fmt(start), fmt(end)];
  }

  const fmtDate = (date) => {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  };
  return [fmtDate(start), fmtDate(end)];
}

/** 当月 YYYY-MM-DD 范围（兼容旧名） */
export function getDefaultMonthDateRange() {
  return getMonthDateRange('date');
}

/** 当月 ISO 时间范围（兼容旧名） */
export function getCurrentMonthRange() {
  return getMonthDateRange('iso');
}
