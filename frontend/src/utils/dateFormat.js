import { ElMessage } from 'element-plus';
import { getTimezone } from '../api/mlModel';

// 时区缓存（避免重复请求）
let cachedTimezone = 'Asia/Shanghai'; // 默认值
let timezoneInitialized = false;
let timezonePromise = null;

/**
 * 初始化时区配置（在用户登录后调用）
 * @returns {Promise<void>}
 */
export const initTimezone = async () => {
  if (timezoneInitialized) {
    return;
  }
  
  // 直接尝试获取时区配置，如果失败（如未登录）则使用默认值
  // 系统使用 HttpOnly Cookie，axios 会自动携带认证信息
  if (!timezonePromise) {
    timezonePromise = getTimezone().then(tz => {
      cachedTimezone = tz;
      timezoneInitialized = true;
      return tz;
    }).catch(() => {
      // 如果获取失败（如未登录或网络错误），使用默认值
      cachedTimezone = 'Asia/Shanghai';
      timezoneInitialized = true;
      return cachedTimezone;
    });
  }
  
  return timezonePromise;
};

/**
 * 格式化日期时间（同步版本，使用缓存的时区）
 * @param {string} dateString - 日期字符串（UTC 时间）
 * @returns {string} 格式化后的日期字符串（应用配置的时区）
 */
export const formatDate = (dateString) => {
  if (!dateString) return '-';
  const date = new Date(dateString);
  // 使用缓存的时区或默认值
  return date.toLocaleString('zh-CN', {
    timeZone: cachedTimezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
};

/**
 * 格式化日期时间（完整格式，同步版本）
 * @param {string} dateString - 日期字符串（UTC 时间）
 * @returns {string} 格式化后的日期时间字符串（应用配置的时区）
 */
export const formatDateTime = (dateString) => {
  if (!dateString) return '-';
  const date = new Date(dateString);
  // 使用缓存的时区或默认值
  return date.toLocaleString('zh-CN', {
    timeZone: cachedTimezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

/**
 * 复制文本到剪贴板
 * @param {string} text - 要复制的文本
 * @returns {Promise<boolean>} 是否复制成功
 */
export const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success('已复制到剪贴板');
    return true;
  } catch (error) {
    ElMessage.error('复制失败');
    return false;
  }
};

