/**
 * 版本检查工具
 * 对比「JS 包内构建版本」与「服务端 version.json」，不一致时自动刷新
 */
import axios from 'axios';
import { ElMessage } from 'element-plus';

/** 构建时由 vite-plugin-version 注入，与 dist/version.json 一致 */
const BUILD_VERSION = typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'dev';

// 当前运行中的构建版本（固定为包内版本，不从服务端初始化）
let currentVersion = BUILD_VERSION;
// 是否已初始化
let isInitialized = false;
// 是否正在检查
let isChecking = false;
// 路由/轮询清理函数
let routeWatcher = null;
let removeRouterGuard = null;
let loginPollTimer = null;
let reloadScheduled = false;
// 节流相关变量
let lastCheckTime = 0;
let throttleTimer = null;
// 性能监控相关变量
const performanceMetrics = {
  totalChecks: 0,              // 总检查次数
  successfulChecks: 0,          // 成功检查次数
  failedChecks: 0,             // 失败检查次数
  updatesDetected: 0,          // 检测到更新的次数
  throttledChecks: 0,          // 被节流的检查次数
  totalCheckTime: 0,           // 总检查时间（毫秒）
  averageCheckTime: 0,        // 平均检查时间（毫秒）
  lastCheckTime: 0,            // 上次检查耗时（毫秒）
  lastCheckTimestamp: 0,       // 上次检查时间戳
};
// 离线检测相关变量
let isOnline = navigator.onLine;
let offlineEventListener = null;
let onlineEventListener = null;
// 回调函数
const callbacks = {
  onUpdate: null,        // 检测到更新时的回调
  onRollback: null,      // 检测到回退时的回调
  onError: null,          // 发生错误时的回调
  onCheckStart: null,    // 开始检查时的回调
  onCheckComplete: null,  // 检查完成时的回调
};
// 重试配置
const RETRY_CONFIG = {
  maxRetries: 3,           // 最大重试次数
  retryDelay: 1000,        // 重试延迟（毫秒）
  retryableErrors: ['ECONNABORTED', 'ETIMEDOUT', 'ECONNRESET', 'ENETDOWN'],  // 可重试的错误类型
};
// 节流配置
const THROTTLE_CONFIG = {
  enabled: true,           // 是否启用节流
  interval: 5000,          // 节流间隔（毫秒），5秒内只检查一次
};

// 登录页轮询间隔（毫秒）
const DEFAULT_POLL_INTERVAL = 60000;

const isLoginPath = (path) => path === '/login' || path === '/';

/**
 * 打印日志（使用console.log，确保在开发环境也能看到）
 */
const log = {
  debug: (...args) => console.log('[版本检查-DEBUG]', ...args),
  info: (...args) => console.log('[版本检查-INFO]', ...args),
  warn: (...args) => console.warn('[版本检查-WARN]', ...args),
  error: (...args) => console.error('[版本检查-ERROR]', ...args),
};

/**
 * 加载当前版本号（带重试机制）
 * @param {number} retryCount 当前重试次数
 * @returns {Promise<string|null>} 版本号
 */
const loadCurrentVersion = async (retryCount = 0) => {
  // 检查网络状态
  if (!isOnline) {
    log.warn('网络离线，跳过版本检查');
    return null;
  }

  try {
    // 使用时间戳 + 随机数作为缓存破坏器，确保获取最新版本
    // 随机数可以防止在同一毫秒内多次请求时缓存问题
    const cacheBuster = `${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    const response = await axios.get('/version.json', {
      params: { _t: cacheBuster },
      timeout: 5000,
    });

    if (response.data && response.data.version) {
      log.debug('成功加载版本号:', response.data.version);
      return response.data.version;
    }

    log.warn('版本文件格式不正确，缺少 version 字段');
    return null;
  } catch (error) {
    // 记录详细的错误信息
    const errorDetails = {
      message: error.message,
      code: error.code,
      status: error.response?.status,
      statusText: error.response?.statusText,
      url: error.config?.url,
      method: error.config?.method,
      retryCount,
    };

    // 判断是否可重试
    const isRetryable = RETRY_CONFIG.retryableErrors.includes(error.code) ||
      error.code === 'ECONNABORTED' ||
      !error.response;  // 网络错误

    if (isRetryable && retryCount < RETRY_CONFIG.maxRetries) {
      log.warn(`加载版本号失败，准备第 ${retryCount + 1} 次重试...`, errorDetails);

      // 延迟后重试
      await new Promise(resolve => setTimeout(resolve, RETRY_CONFIG.retryDelay * (retryCount + 1)));
      return loadCurrentVersion(retryCount + 1);
    }

    // 超过最大重试次数或不可重试的错误
    if (error.code === 'ECONNABORTED') {
      log.error('加载版本号超时，已达到最大重试次数:', errorDetails);
    } else if (error.response) {
      log.error('加载版本号失败，服务器返回错误:', errorDetails);
    } else if (error.request) {
      log.error('加载版本号失败，网络错误，已达到最大重试次数:', errorDetails);
    } else {
      log.error('加载版本号失败:', errorDetails);
    }

    return null;
  }
};

/**
 * 检查是否有新版本（带节流机制）
 * @param {boolean} bypassThrottle 是否绕过节流，默认 false
 * @returns {Promise<boolean>} 是否有新版本
 */
const checkForUpdate = async (bypassThrottle = false) => {
  if (isChecking) {
    log.debug('版本检查正在进行中，跳过本次检查');
    performanceMetrics.throttledChecks++;
    return false;
  }

  // 节流检查
  if (THROTTLE_CONFIG.enabled && !bypassThrottle) {
    const now = Date.now();
    const timeSinceLastCheck = now - lastCheckTime;

    if (timeSinceLastCheck < THROTTLE_CONFIG.interval) {
      log.debug(`距离上次检查仅 ${timeSinceLastCheck}ms，跳过本次检查（节流间隔：${THROTTLE_CONFIG.interval}ms）`);
      performanceMetrics.throttledChecks++;
      return false;
    }
  }

  isChecking = true;
  lastCheckTime = Date.now();
  const checkStartTime = performance.now();
  performanceMetrics.totalChecks++;
  performanceMetrics.lastCheckTimestamp = lastCheckTime;

  // 调用开始检查回调
  if (callbacks.onCheckStart) {
    try {
      callbacks.onCheckStart();
    } catch (error) {
      log.error('onCheckStart 回调执行失败:', error);
    }
  }

  try {
    const latestVersion = await loadCurrentVersion();

    if (!latestVersion) {
      performanceMetrics.failedChecks++;

      // 调用错误回调
      if (callbacks.onError) {
        try {
          callbacks.onError(new Error('无法加载版本号'));
        } catch (error) {
          log.error('onError 回调执行失败:', error);
        }
      }

      return false;
    }

    performanceMetrics.successfulChecks++;

    // 包内构建版本 vs 服务端最新版本
    if (latestVersion !== currentVersion) {
      const isUpdate = latestVersion > currentVersion;
      const isRollback = latestVersion < currentVersion;

      if (isUpdate) {
        log.info('检测到新版本，准备刷新页面', {
          current: currentVersion,
          latest: latestVersion,
        });

        // 调用更新回调
        if (callbacks.onUpdate) {
          try {
            callbacks.onUpdate({
              currentVersion,
              latestVersion,
            });
          } catch (error) {
            log.error('onUpdate 回调执行失败:', error);
          }
        }
      } else if (isRollback) {
        log.warn('检测到版本回退，准备刷新页面', {
          current: currentVersion,
          latest: latestVersion,
        });

        // 调用回退回调
        if (callbacks.onRollback) {
          try {
            callbacks.onRollback({
              currentVersion,
              latestVersion,
            });
          } catch (error) {
            log.error('onRollback 回调执行失败:', error);
          }
        }
      }

      performanceMetrics.updatesDetected++;
      return true;
    }

    return false;
  } catch (error) {
    log.warn('检查版本更新失败:', error.message);
    performanceMetrics.failedChecks++;

    // 调用错误回调
    if (callbacks.onError) {
      try {
        callbacks.onError(error);
      } catch (callbackError) {
        log.error('onError 回调执行失败:', callbackError);
      }
    }

    return false;
  } finally {
    isChecking = false;

    // 记录性能指标
    const checkEndTime = performance.now();
    const checkDuration = checkEndTime - checkStartTime;
    performanceMetrics.totalCheckTime += checkDuration;
    performanceMetrics.lastCheckTime = checkDuration;
    performanceMetrics.averageCheckTime = performanceMetrics.totalCheckTime / performanceMetrics.totalChecks;

    log.debug(`版本检查完成，耗时：${checkDuration.toFixed(2)}ms`);

    // 调用检查完成回调
    if (callbacks.onCheckComplete) {
      try {
        callbacks.onCheckComplete({
          duration: checkDuration,
          success: performanceMetrics.successfulChecks > 0,
        });
      } catch (error) {
        log.error('onCheckComplete 回调执行失败:', error);
      }
    }
  }
};

/**
 * 刷新页面
 * @param {boolean} showMessage 是否显示提示消息
 * @param {number} delay 刷新延迟时间（毫秒），默认 2000
 */
const reloadPage = (showMessage = true, delay = 2000) => {
  if (reloadScheduled) {
    return;
  }
  reloadScheduled = true;

  if (showMessage) {
    ElMessage.info({
      message: '检测到新版本，页面即将刷新...',
      duration: delay,
    });
  }

  log.info('正在刷新页面以加载新版本...');

  // 延迟刷新，让用户看到提示
  setTimeout(() => {
    // 使用 location.reload() 强制刷新，清除缓存
    window.location.reload();
  }, showMessage ? delay : 500);
};

/**
 * 初始化版本检查（登录页进入时检查 + 定时轮询）
 * @param {Object} options 配置选项
 * @param {boolean} options.enabled 是否启用版本检查，默认 true
 * @param {boolean} options.showMessage 检测到更新时是否显示提示消息，默认 true
 * @param {number} options.reloadDelay 刷新延迟时间（毫秒），默认 2000
 * @param {boolean} options.enableThrottle 是否启用节流，默认 true
 * @param {number} options.throttleInterval 节流间隔（毫秒），默认 5000
 * @param {boolean} options.enableOfflineDetection 是否启用离线检测，默认 true
 * @param {number} options.pollInterval 登录页轮询间隔（毫秒），默认 60000
 * @param {import('vue-router').Router} [options.router] Vue Router 实例
 */
export const initVersionCheck = (options = {}) => {
  if (isInitialized) {
    log.warn('版本检查已经初始化，跳过重复初始化');
    return;
  }

  const {
    enabled = true,
    showMessage = true,
    reloadDelay = 2000,
    enableThrottle = true,
    throttleInterval = 5000,
    enableOfflineDetection = true,
    pollInterval = DEFAULT_POLL_INTERVAL,
    router = null,
  } = options;
  isInitialized = true;

  // 配置节流
  THROTTLE_CONFIG.enabled = enableThrottle;
  THROTTLE_CONFIG.interval = throttleInterval;

  // 初始化网络状态监听
  if (enableOfflineDetection) {
    offlineEventListener = () => {
      isOnline = false;
      log.warn('网络已断开');
    };

    onlineEventListener = () => {
      isOnline = true;
      log.info('网络已恢复');
    };

    window.addEventListener('offline', offlineEventListener);
    window.addEventListener('online', onlineEventListener);
    log.info('离线检测已启用');
  }

  if (!enabled) {
    log.debug('版本检查已禁用');
    return;
  }

  if (!currentVersion || currentVersion === 'dev') {
    log.warn('构建版本无效，版本检查已跳过');
    return;
  }

  log.debug('版本检查已初始化，包内构建版本:', currentVersion);
  if (enableThrottle) {
    log.debug(`节流已启用，间隔：${throttleInterval}ms`);
  }

  const runLoginPageCheck = () => {
    log.debug('登录页检查版本更新...');
    checkForUpdate().then((hasUpdate) => {
      if (hasUpdate) {
        reloadPage(showMessage, reloadDelay);
      }
    });
  };

  const stopLoginPolling = () => {
    if (loginPollTimer) {
      clearInterval(loginPollTimer);
      loginPollTimer = null;
    }
  };

  const startLoginPolling = () => {
    stopLoginPolling();
    if (pollInterval > 0) {
      loginPollTimer = setInterval(runLoginPageCheck, pollInterval);
    }
  };

  const handleLoginRoute = (path) => {
    if (!isLoginPath(path)) {
      stopLoginPolling();
      return;
    }
    runLoginPageCheck();
    startLoginPolling();
  };

  handleLoginRoute(window.location.pathname);

  const handlePopState = () => {
    handleLoginRoute(window.location.pathname);
  };
  window.addEventListener('popstate', handlePopState);
  routeWatcher = () => {
    window.removeEventListener('popstate', handlePopState);
  };

  if (router && typeof router.afterEach === 'function') {
    removeRouterGuard = router.afterEach((to) => {
      handleLoginRoute(to.path);
    });
  }

  log.info('版本检查已启用：登录页进入时检查，并每 %d 秒轮询', pollInterval / 1000);
};

/**
 * 停止版本检查
 * 清理路由监听器和网络事件监听器，防止内存泄漏
 */
export const stopVersionCheck = () => {
  isInitialized = false;
  reloadScheduled = false;

  if (loginPollTimer) {
    clearInterval(loginPollTimer);
    loginPollTimer = null;
  }

  if (removeRouterGuard) {
    removeRouterGuard();
    removeRouterGuard = null;
    log.info('路由守卫已清理');
  }

  // 清理 popstate 监听器
  if (routeWatcher) {
    routeWatcher();
    routeWatcher = null;
    log.info('路由监听器已清理');
  }

  // 清理网络事件监听器
  if (offlineEventListener) {
    window.removeEventListener('offline', offlineEventListener);
    offlineEventListener = null;
  }

  if (onlineEventListener) {
    window.removeEventListener('online', onlineEventListener);
    onlineEventListener = null;
  }

  log.info('版本检查已停止');
};

/**
 * 手动检查更新
 * @param {boolean} showMessage 是否显示提示消息
 * @param {number} reloadDelay 刷新延迟时间（毫秒），默认 2000
 * @returns {Promise<boolean>} 是否有新版本
 */
export const manualCheckUpdate = async (showMessage = true, reloadDelay = 2000) => {
  const hasUpdate = await checkForUpdate();
  if (hasUpdate) {
    reloadPage(showMessage, reloadDelay);
    return true;
  }
  return false;
};

/**
 * 获取性能指标
 * @returns {Object} 性能指标对象
 */
export const getPerformanceMetrics = () => {
  return {
    ...performanceMetrics,
    successRate: performanceMetrics.totalChecks > 0
      ? (performanceMetrics.successfulChecks / performanceMetrics.totalChecks * 100).toFixed(2) + '%'
      : '0%',
  };
};

/**
 * 打印性能指标
 */
export const printPerformanceMetrics = () => {
  const metrics = getPerformanceMetrics();
  log.info('=== 版本检查性能指标 ===');
  log.info('总检查次数:', metrics.totalChecks);
  log.info('成功检查次数:', metrics.successfulChecks);
  log.info('失败检查次数:', metrics.failedChecks);
  log.info('检测到更新次数:', metrics.updatesDetected);
  log.info('被节流次数:', metrics.throttledChecks);
  log.info('成功率:', metrics.successRate);
  log.info('平均检查时间:', metrics.averageCheckTime.toFixed(2) + 'ms');
  log.info('上次检查耗时:', metrics.lastCheckTime.toFixed(2) + 'ms');
  log.info('上次检查时间戳:', new Date(metrics.lastCheckTimestamp).toISOString());
  log.info('========================');
};

/**
 * 设置回调函数
 * @param {Object} options 回调函数配置
 * @param {Function} options.onUpdate 检测到更新时的回调
 * @param {Function} options.onRollback 检测到回退时的回调
 * @param {Function} options.onError 发生错误时的回调
 * @param {Function} options.onCheckStart 开始检查时的回调
 * @param {Function} options.onCheckComplete 检查完成时的回调
 */
export const setCallbacks = (options = {}) => {
  if (options.onUpdate) {
    callbacks.onUpdate = options.onUpdate;
  }

  if (options.onRollback) {
    callbacks.onRollback = options.onRollback;
  }

  if (options.onError) {
    callbacks.onError = options.onError;
  }

  if (options.onCheckStart) {
    callbacks.onCheckStart = options.onCheckStart;
  }

  if (options.onCheckComplete) {
    callbacks.onCheckComplete = options.onCheckComplete;
  }

  log.debug('回调函数已设置');
};

/**
 * 健康检查
 * 检查版本检查系统是否正常工作
 * @returns {Promise<Object>} 健康检查结果
 */
export const healthCheck = async () => {
  const health = {
    status: 'healthy',
    checks: {
      initialized: isInitialized,
      hasCurrentVersion: currentVersion !== null,
      isOnline: isOnline,
      routeWatcherActive: routeWatcher !== null || removeRouterGuard !== null,
      buildVersion: BUILD_VERSION,
      loginPollingActive: loginPollTimer !== null,
      offlineDetectionActive: offlineEventListener !== null && onlineEventListener !== null,
    },
    metrics: getPerformanceMetrics(),
    config: {
      throttleEnabled: THROTTLE_CONFIG.enabled,
      throttleInterval: THROTTLE_CONFIG.interval,
      retryMaxRetries: RETRY_CONFIG.maxRetries,
      retryDelay: RETRY_CONFIG.retryDelay,
    },
    issues: [],
  };

  // 检查各个组件的状态
  if (!health.checks.initialized) {
    health.status = 'unhealthy';
    health.issues.push('版本检查未初始化');
  }

  if (!health.checks.hasCurrentVersion) {
    health.status = 'warning';
    health.issues.push('没有当前版本号');
  }

  if (!health.checks.isOnline) {
    health.status = 'warning';
    health.issues.push('网络离线');
  }

  if (!health.checks.routeWatcherActive && isInitialized) {
    health.status = 'warning';
    health.issues.push('路由监听器未激活');
  }

  // 检查性能指标
  if (health.metrics.totalChecks > 0) {
    const successRate = parseFloat(health.metrics.successRate);
    if (successRate < 50) {
      health.status = 'unhealthy';
      health.issues.push(`成功率过低：${successRate}%`);
    } else if (successRate < 80) {
      health.status = 'warning';
      health.issues.push(`成功率较低：${successRate}%`);
    }

    if (health.metrics.averageCheckTime > 5000) {
      health.status = 'warning';
      health.issues.push(`平均检查时间过长：${health.metrics.averageCheckTime.toFixed(2)}ms`);
    }
  }

  return health;
};
