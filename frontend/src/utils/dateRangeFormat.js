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

/**
 * 指定日期所在自然月的 YYYY-MM-DD 范围。
 * @param {string} dateStr
 * @returns {[string, string]}
 */
export function getMonthDateRangeForDate(dateStr) {
  const [y, m] = String(dateStr).slice(0, 10).split('-').map(Number);
  const start = `${y}-${String(m).padStart(2, '0')}-01`;
  const lastDay = new Date(y, m, 0).getDate();
  const end = `${y}-${String(m).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
  return [start, end];
}

/**
 * 广告数据页初次加载的默认日期范围：
 * - 有数据且与本月相交 → 本月
 * - 否则 → 最近有数据的那个月
 * @param {string|null|undefined} minDate
 * @param {string|null|undefined} maxDate
 */
export function resolveInitialAdDataDateRange(minDate, maxDate) {
  if (!minDate || !maxDate) {
    return getDefaultMonthDateRange();
  }
  const [monthStart, monthEnd] = getDefaultMonthDateRange();
  if (monthStart <= maxDate && monthEnd >= minDate) {
    return [monthStart, monthEnd];
  }
  return getMonthDateRangeForDate(maxDate);
}

/** 判断两个日期范围是否相同（YYYY-MM-DD） */
export function isSameDateRange(rangeA, rangeB) {
  if (!Array.isArray(rangeA) || !Array.isArray(rangeB) || rangeA.length !== 2 || rangeB.length !== 2) {
    return false;
  }
  return rangeA[0] === rangeB[0] && rangeA[1] === rangeB[1];
}
