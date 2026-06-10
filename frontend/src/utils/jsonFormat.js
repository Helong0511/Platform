/**
 * JSON 格式化工具
 * @file utils/jsonFormat.js
 */

/**
 * 将 JSON 字符串或对象格式化为缩进可读文本。
 * @param {*} value - JSON 字符串或已解析对象
 * @param {*} [fallback=''] - 空值时的默认展示
 * @returns {string}
 */
export function formatJson(value, fallback = '') {
  if (value === null || value === undefined || value === '') {
    return fallback || String(value ?? '');
  }
  try {
    const obj = typeof value === 'string' ? JSON.parse(value) : value;
    return JSON.stringify(obj, null, 2);
  } catch {
    return typeof value === 'string' ? value : String(value);
  }
}
