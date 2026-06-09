/**
 * 比率转百分比，如 0.15 → "15.00%"
 * @param {number|null|undefined} value
 * @param {{ empty?: string }} [options] empty 为 null/undefined 时的展示，默认 "0.00%"
 */
export function formatRatioAsPercent(value, options = {}) {
  const { empty = '0.00%' } = options;
  if (value === null || value === undefined) {
    return empty === null ? '-' : empty;
  }
  const num = Number(value);
  if (Number.isNaN(num)) {
    return empty === null ? '-' : empty;
  }
  return `${(num * 100).toFixed(2)}%`;
}

/**
 * 已为百分数的数值，如 15.5 → "15.50%"
 */
export function formatPercentNumber(value, options = {}) {
  const { empty = '0.00%' } = options;
  if (value === null || value === undefined) {
    return empty;
  }
  const num = Number(value);
  if (Number.isNaN(num)) {
    return empty;
  }
  return `${num.toFixed(2)}%`;
}

/**
 * Element Plus 表格 formatter：(_row, _column, value) => string
 * @param {{ asRatio?: boolean }} [options] asRatio=true 时按 0–1 比率处理
 */
export function createPercentTableFormatter(options = {}) {
  const { asRatio = false } = options;
  const fmt = asRatio ? formatRatioAsPercent : formatPercentNumber;
  return (_row, _column, value) => fmt(value);
}
