/**
 * 日期格式化工具函数
 * 为了兼容性，从 dateFormat.js 重新导出
 */
import { formatDate as formatDateFromDateFormat } from './dateFormat'

/**
 * 格式化日期
 * @param {string|Date} date - 日期字符串或Date对象
 * @param {string} format - 格式字符串（可选，当前实现忽略此参数，使用默认格式）
 * @returns {string} 格式化后的日期字符串
 */
export function formatDate(date, format) {
  // dateFormat.js 中的 formatDate 只接受一个参数
  // 这里忽略 format 参数以保持兼容性
  return formatDateFromDateFormat(date)
}

