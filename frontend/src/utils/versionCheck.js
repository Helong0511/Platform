/**
 * 版本检查工具
 * 用于检测前端是否有新版本，如果有则自动刷新页面
 */
import axios from 'axios';
import { logger } from './logger';
import { ElMessage } from 'element-plus';

// 当前版本号（从版本文件加载）
let currentVersion = null;
// 是否已初始化
let isInitialized = false;
// 是否正在检查
let isChecking = false;

/**
 * 加载当前版本号
 * @returns {Promise<string|null>} 版本号
 */
const loadCurrentVersion = async () => {
  try {
    // 使用时间戳作为缓存破坏器，确保获取最新版本
    const response = await axios.get('/version.json', {
      params: { _t: Date.now() },
      timeout: 5000,
    });
    
    if (response.data && response.data.version) {
      return response.data.version;
    }
    return null;
  } catch (error) {
    logger.warn('加载版本号失败:', error.message);
    return null;
  }
};

/**
 * 检查是否有新版本
 * @returns {Promise<boolean>} 是否有新版本
 */
const checkForUpdate = async () => {
  if (isChecking) {
    return false;
  }

  isChecking = true;
  try {
    const latestVersion = await loadCurrentVersion();
    
    if (!latestVersion) {
      return false;
    }

    // 如果还没有当前版本，设置为最新版本
    if (!currentVersion) {
      currentVersion = latestVersion;
      logger.debug('初始化版本号:', currentVersion);
      return false;
    }

    // 如果版本号不同，说明有新版本
    if (latestVersion !== currentVersion) {
      logger.info('检测到新版本，准备刷新页面', {
        current: currentVersion,
        latest: latestVersion,
      });
      return true;
    }

    return false;
  } catch (error) {
    logger.warn('检查版本更新失败:', error.message);
    return false;
  } finally {
    isChecking = false;
  }
};

/**
 * 刷新页面
 * @param {boolean} showMessage 是否显示提示消息
 */
const reloadPage = (showMessage = true) => {
  if (showMessage) {
    ElMessage.info({
      message: '检测到新版本，页面即将刷新...',
      duration: 2000,
    });
  }
  
  logger.info('正在刷新页面以加载新版本...');
  
  // 延迟刷新，让用户看到提示
  setTimeout(() => {
    // 使用 location.reload() 强制刷新，清除缓存
    window.location.reload();
  }, showMessage ? 2000 : 500);
};

/**
 * 初始化版本检查（仅在页面打开时检查一次）
 * @param {Object} options 配置选项
 * @param {boolean} options.enabled 是否启用版本检查，默认 true
 * @param {boolean} options.showMessage 检测到更新时是否显示提示消息，默认 true
 */
export const initVersionCheck = async (options = {}) => {
  if (isInitialized) {
    logger.warn('版本检查已经初始化，跳过重复初始化');
    return;
  }

  const { 
    enabled = true,
    showMessage = true,
  } = options;
  isInitialized = true;

  if (!enabled) {
    logger.debug('版本检查已禁用');
    return;
  }

  // 加载初始版本号
  currentVersion = await loadCurrentVersion();
  if (currentVersion) {
    logger.debug('版本检查已初始化，当前版本:', currentVersion);
  } else {
    logger.warn('无法加载初始版本号，版本检查可能无法正常工作');
    return;
  }

  // 立即检查一次是否有新版本
  const hasUpdate = await checkForUpdate();
  if (hasUpdate) {
    // 刷新页面
    reloadPage(showMessage);
  } else {
    logger.info('版本检查完成，当前已是最新版本');
  }
};

/**
 * 停止版本检查
 */
export const stopVersionCheck = () => {
  isInitialized = false;
  logger.info('版本检查已停止');
};

/**
 * 手动检查更新
 * @param {boolean} showMessage 是否显示提示消息
 * @returns {Promise<boolean>} 是否有新版本
 */
export const manualCheckUpdate = async (showMessage = true) => {
  const hasUpdate = await checkForUpdate();
  if (hasUpdate) {
    reloadPage(showMessage);
    return true;
  }
  return false;
};
