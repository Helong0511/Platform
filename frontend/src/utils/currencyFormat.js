/**
 * 货币与广告表格金额格式化
 * @file utils/currencyFormat.js
 *
 * 默认 USD；支持按记录自身 ISO 4217 币种格式化，避免跨币种金额显示错误。
 * 后端 Decimal 金额优先以十进制字符串传入，避免经 JavaScript Number 丢失精度。
 */

const formatUsdFixed = (value) => {
  if (value === null || value === undefined || value === '') return '$0.00';
  try {
    // Intl.NumberFormat 在现代浏览器中可直接按十进制字符串格式化，
    // 不必先转换为 IEEE-754 Number。
    return '$' + new Intl.NumberFormat('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value);
  } catch {
    // 极端兼容场景下保留后端原始十进制文本，不用 Number 二次损失精度。
    return `$${String(value)}`;
  }
};

/**
 * 将金额格式化为指定 ISO 4217 币种。
 * @param {string|number} value - 金额；财务金额优先传十进制字符串
 * @param {string} currency - ISO 4217 币种代码，缺失时 USD
 * @returns {string} 格式化后的货币文本，空值返回 '-'
 */
export function formatCurrency(value, currency = 'USD') {
  if (value === null || value === undefined || value === '') return '-';
  const code = String(currency || 'USD').trim().toUpperCase() || 'USD';
  try {
    return new Intl.NumberFormat('zh-CN', {
      style: 'currency',
      currency: code,
      currencyDisplay: 'code'
    }).format(value);
  } catch {
    // 不将 Decimal 字符串强制转成 Number，避免大金额精度丢失。
    return `${String(value)} ${code}`;
  }
}

/** Element Plus 表格列 formatter：USD 固定两位小数 */
export function formatAdTableCurrency(_row, _column, value) {
  return formatAdTableCurrencyAmount(value);
}

/** USD 金额格式化（合计行等）；字符串输入可避免 Number 精度损失 */
export function formatAdTableCurrencyAmount(value) {
  return formatUsdFixed(value);
}

/** TB 搜索数据等简单 USD 展示 */
export function formatTbCurrency(val) {
  return formatUsdFixed(val);
}
