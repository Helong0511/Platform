/**
 * 日志工具
 * 在生产环境中禁用 console.log，开发环境中保留
 */

const isDevelopment = import.meta.env.MODE === 'development' || import.meta.env.DEV;

class Logger {
  log(...args) {
    if (isDevelopment) {
      console.log('[LOG]', ...args);
    }
  }

  error(...args) {
    // 错误始终记录
    console.error('[ERROR]', ...args);
  }

  warn(...args) {
    // 警告始终记录
    console.warn('[WARN]', ...args);
  }

  info(...args) {
    if (isDevelopment) {
      console.info('[INFO]', ...args);
    }
  }

  debug(...args) {
    if (isDevelopment) {
      console.debug('[DEBUG]', ...args);
    }
  }
}

export const logger = new Logger();
export default logger;

