/**
 * 页面认证检查 Composable
 * 用于在页面加载前检查认证状态，避免token过期后长时间转圈
 */
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../store';
import { ElMessage } from 'element-plus';

export function usePageAuth() {
  const router = useRouter();
  const authStore = useAuthStore();

  /**
   * 检查认证状态，如果未认证则跳转到登录页
   * @returns {boolean} 是否已认证
   */
  const checkAuthBeforeLoad = () => {
    // 检查是否已认证（现在基于 HttpOnly Cookie，JS 无法直接读取 token）
    // 因此这里依赖 store 中的状态，初始化时会根据 userInfo 判断
    if (!authStore.isAuthenticated) {
      ElMessage.warning('请先登录');
      router.push('/login').catch(() => {
        window.location.href = '/login';
      });
      return false;
    }

    // 确保store状态同步
    if (!authStore.isAuthenticated) {
      authStore.checkAuth();
      if (!authStore.isAuthenticated) {
        ElMessage.warning('登录已过期，请重新登录');
        router.push('/login').catch(() => {
          window.location.href = '/login';
        });
        return false;
      }
    }

    return true;
  };

  /**
   * 创建带超时保护的Promise
   * @param {Promise} promise - 要保护的Promise
   * @param {number} timeout - 超时时间（毫秒），默认20秒
   * @param {string} errorMessage - 超时错误消息
   * @returns {Promise} 带超时保护的Promise
   */
  const withTimeout = (promise, timeout = 20000, errorMessage = '请求超时，请检查网络连接') => {
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => {
        reject(new Error(errorMessage));
      }, timeout);
    });

    return Promise.race([promise, timeoutPromise]);
  };

  /**
   * 安全执行异步操作，自动处理401错误
   * @param {Function} asyncFn - 异步函数
   * @param {Object} options - 配置选项
   * @returns {Promise} 执行结果
   */
  const safeAsync = async (asyncFn, options = {}) => {
    const {
      timeout = 20000,
      timeoutMessage = '操作超时，请检查网络连接',
      onError = null,
      stopLoading = null
    } = options;

    try {
      return await withTimeout(asyncFn(), timeout, timeoutMessage);
    } catch (error) {
      // 401错误已在拦截器中处理，这里只需要停止loading
      if (error.response?.status === 401) {
        if (stopLoading && typeof stopLoading === 'function') {
          stopLoading();
        }
        return null;
      }

      // 超时错误
      if (error.message && error.message.includes('超时')) {
        if (stopLoading && typeof stopLoading === 'function') {
          stopLoading();
        }
        if (onError && typeof onError === 'function') {
          onError(error);
        }
        throw error;
      }

      // 其他错误
      if (onError && typeof onError === 'function') {
        onError(error);
      }
      throw error;
    }
  };

  return {
    checkAuthBeforeLoad,
    withTimeout,
    safeAsync,
    isAuthenticated: computed(() => authStore.isAuthenticated),
    isAdmin: computed(() => authStore.isAdmin)
  };
}

