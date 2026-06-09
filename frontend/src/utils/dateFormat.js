/**
 * 日期时间格式化工具（前端展示用）。
 *
 * 从后端 app-config 拉取业务时区并缓存，将 ISO/时间戳格式化为本地可读字符串。
 * 须在用户登录后调用 initTimezone() 初始化时区，否则默认 Asia/Shanghai。
 */
import { getTimezone } from '../api/app-config';

// 时区缓存（避免重复请求）
let cachedTimezone = 'Asia/Shanghai';
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

  if (!timezonePromise) {
    timezonePromise = getTimezone().then((tz) => {
      cachedTimezone = tz;
      timezoneInitialized = true;
      return tz;
    }).catch(() => {
      cachedTimezone = 'Asia/Shanghai';
      timezoneInitialized = true;
      return cachedTimezone;
    });
  }

  return timezonePromise;
};

/**
 * 格式化日期时间（同步版本，使用缓存的时区）
 */
export const formatDate = (dateString) => {
  if (!dateString) return '-';
  const date = new Date(dateString);
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
 * 格式化日期时间（含秒）
 */
export const formatDateTime = (dateString) => {
  if (!dateString) return '-';
  const date = new Date(dateString);
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
 * 仅日期（产品分配历史等）
 */
export const formatDateOnly = (dateStr) => {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  return date.toLocaleDateString('zh-CN', {
    timeZone: cachedTimezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  });
};
