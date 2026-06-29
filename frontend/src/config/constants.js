/**
 * 全局配置常量
 * @file config/constants.js
 *
 * 集中管理表单校验、分页、防抖、缓存 TTL、状态映射等硬编码值，
 * 避免在组件与 composable 中散落魔法数字。
 */

/** 表单字段长度校验阈值 */
export const VALIDATION = {
  USERNAME_MIN_LENGTH: 3,
  USERNAME_MAX_LENGTH: 50,
  PASSWORD_MIN_LENGTH: 8,
  PASSWORD_MAX_LENGTH: 32,
  EMAIL_MAX_LENGTH: 100,
  NAME_MAX_LENGTH: 100
};

/** 列表分页默认配置 */
export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 20,
  PAGE_SIZES: [10, 20, 50, 100],
  DEFAULT_PAGE: 1
};

/** 输入防抖延迟（毫秒） */
export const DEBOUNCE = {
  SEARCH: 300,
  FORM_SUBMIT: 500
};

/** 前端缓存过期时间（秒） */
export const CACHE = {
  SHORT: 60,      // 1 分钟
  MEDIUM: 300,    // 5 分钟
  LONG: 3600      // 1 小时
};

/** HTTP 请求超时（毫秒），区分移动端与桌面端 */
export const API_TIMEOUT = {
  MOBILE: 30000,
  DESKTOP: 15000
};

/** 业务状态 → Element Plus 标签类型与中文文案 */
export const STATUS_MAP = {
  active: { type: 'success', text: '激活' },
  paused: { type: 'warning', text: '暂停' },
  archived: { type: 'info', text: '归档' },
  inactive: { type: 'danger', text: '禁用' }
};

/** 用户角色 → Element Plus 标签类型与中文文案 */
export const ROLE_MAP = {
  admin: { type: 'danger', text: '管理员' },
  client: { type: 'primary', text: '客户' }
};
