/**
 * 缓存管理页展示格式化
 * @file utils/cacheFormat.js
 *
 * 将缓存大小、过期时间、类型等原始值转为用户友好的展示文案。
 */

/** 将字节数格式化为 B/KB/MB/GB */
export function formatCacheSize(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
}

/** 将过期时间戳转为相对时间描述（如「5分钟」「已过期」） */
export function formatCacheExpireTime(expireTime) {
  if (!expireTime) return '永不过期';
  const diff = expireTime - Date.now();
  if (diff < 0) return '已过期';
  if (diff < 60000) return '不到1分钟';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时`;
  return `${Math.floor(diff / 86400000)}天`;
}

/**
 * 缓存类型对应的标签颜色。
 */
export function getCacheTypeColor(type) {
  const colorMap = {
    API: 'primary',
    System: 'success',
    User: 'warning',
    Other: 'info',
    ShortLink: 'success',
    Cloak: 'warning',
    Product: 'info',
    Session: 'primary',
    AuditLog: 'danger',
    Task: 'warning',
  };
  return colorMap[type] || 'info';
}

/**
 * 格式化Cache Content。
 */
export function formatCacheContent(content) {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return content;
  }
}
