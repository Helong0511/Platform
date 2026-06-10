/**
 * Postback 转化展示格式化
 * @file utils/postbackFormat.js
 *
 * 重导出货币格式化，并提供 OS、状态等字段的中文映射。
 */
export { formatCurrency } from './currencyFormat';

export function formatOs(os) {
  if (!os) return '-';
  const osMap = {
    IOS: 'iOS',
    ios: 'iOS',
    Android: 'Android',
    android: 'Android',
    iPhone: 'iOS',
    iPad: 'iOS',
    Windows: 'Windows',
    Mac: 'macOS',
    Linux: 'Linux',
  };
  return osMap[os] || os;
}

/**
 * 操作系统类型对应的标签 type。
 */
export function getOsTagType(os) {
  if (!os) return 'info';
  const osLower = os.toLowerCase();
  if (osLower.includes('ios') || osLower.includes('iphone') || osLower.includes('ipad')) {
    return 'primary';
  }
  if (osLower.includes('android')) return 'success';
  if (osLower.includes('windows')) return 'warning';
  if (osLower.includes('mac')) return '';
  return 'info';
}

export { formatJson } from './jsonFormat';
