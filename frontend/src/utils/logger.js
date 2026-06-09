/**
 * 日志工具
 * 在生产环境中禁用 console.log，开发环境中保留
 * 
 * 安全说明：
 * - 生产环境完全禁用所有console输出，防止敏感信息泄露
 * - 开发环境保留所有日志，便于调试
 * - error和warn在生产环境也记录，但可以通过环境变量控制
 */

const isDevelopment = import.meta.env.MODE === 'development' || import.meta.env.DEV;
// 生产环境是否允许错误日志（默认false，完全禁用）
const allowErrorLogInProduction = import.meta.env.VITE_ALLOW_ERROR_LOG === 'true';

class Logger {
  log(...args) {
    if (isDevelopment) {
      console.log('[LOG]', ...args);
    }
    // 生产环境完全禁用
  }

  error(...args) {
    if (isDevelopment || allowErrorLogInProduction) {
      console.error('[ERROR]', ...args);
    }
    // 生产环境默认禁用，防止敏感信息泄露
  }

  warn(...args) {
    if (isDevelopment || allowErrorLogInProduction) {
      console.warn('[WARN]', ...args);
    }
    // 生产环境默认禁用
  }

  info(...args) {
    if (isDevelopment) {
      console.info('[INFO]', ...args);
    }
    // 生产环境完全禁用
  }

  debug(...args) {
    if (isDevelopment) {
      console.debug('[DEBUG]', ...args);
    }
    // 生产环境完全禁用
  }
}

/** 全局日志单例，生产环境默认禁用 console 输出 */
export const logger = new Logger();
/** 默认导出 logger 单例 */
export default logger;

