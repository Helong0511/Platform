/**
 * 全局配置常量
 * 集中管理所有硬编码值
 */

// 验证规则
export const VALIDATION = {
  USERNAME_MIN_LENGTH: 3,
  USERNAME_MAX_LENGTH: 50,
  PASSWORD_MIN_LENGTH: 6,
  PASSWORD_MAX_LENGTH: 32,
  EMAIL_MAX_LENGTH: 100,
  NAME_MAX_LENGTH: 100
};

// 分页配置
export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 20,
  PAGE_SIZES: [10, 20, 50, 100],
  DEFAULT_PAGE: 1
};

// 防抖延迟
export const DEBOUNCE = {
  SEARCH: 300,
  FORM_SUBMIT: 500
};

// 缓存 TTL
export const CACHE = {
  SHORT: 60,      // 1 分钟
  MEDIUM: 300,    // 5 分钟
  LONG: 3600      // 1 小时
};

// API 超时
export const API_TIMEOUT = {
  MOBILE: 30000,
  DESKTOP: 15000
};

// 状态映射
export const STATUS_MAP = {
  active: { type: 'success', text: '激活' },
  paused: { type: 'warning', text: '暂停' },
  archived: { type: 'info', text: '归档' },
  inactive: { type: 'danger', text: '禁用' }
};

// 角色映射
export const ROLE_MAP = {
  admin: { type: 'danger', text: '管理员' },
  client: { type: 'primary', text: '客户' }
};
