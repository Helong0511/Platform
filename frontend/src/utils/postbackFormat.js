/** Postback 转化展示格式化工具 */

export function formatCurrency(value) {
  if (!value && value !== 0) return '-';
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

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

export function formatJson(jsonString) {
  try {
    const obj = typeof jsonString === 'string' ? JSON.parse(jsonString) : jsonString;
    return JSON.stringify(obj, null, 2);
  } catch (_e) {
    return jsonString;
  }
}
