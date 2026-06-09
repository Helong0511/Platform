/**
 * 货币与广告表格金额格式化
 * @file utils/currencyFormat.js
 *
 * 统一 USD 货币展示格式，供表格列 formatter 与统计卡片使用。
 */

/**
 * 将数值格式化为 USD 货币字符串
 * @param {number} value - 金额数值
 * @returns {string} 格式化后的货币文本，空值返回 '-'
 */
export function formatCurrency(value) {
  if (!value && value !== 0) return '-';
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

/** Element Plus 表格列 formatter：$0.00 */
export function formatAdTableCurrency(_row, _column, value) {
  return formatAdTableCurrencyAmount(value);
}

/** 数值转 $X.XX（合计行等） */
export function formatAdTableCurrencyAmount(value) {
  const numValue = Number(value);
  if (Number.isNaN(numValue)) {
    return '$0.00';
  }
  return `$${numValue.toFixed(2)}`;
}

/** TB 搜索数据等简单展示 */
export function formatTbCurrency(val) {
  return val ? `$${Number(val).toFixed(2)}` : '$0.00';
}
