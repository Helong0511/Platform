/**
 * 防抖 + 请求去重的分页列表拉取
 * @file composables/useDebouncedPaginatedFetch.js
 *
 * 封装列表页通用的防抖搜索、并发请求取消与分页参数构建逻辑。
 */
import { ElMessage } from 'element-plus';
import { extractErrorMessage, isErrorHandled } from '../utils/api';

/**
 * @param {Object} options
 * @param {import('vue').Ref<boolean>} options.loading
 * @param {import('vue').Ref} options.pagination { current, size, total }
 * @param {() => Object} options.buildParams
 * @param {(params: Object) => Promise<{data: Array, total: number}>} options.fetchPage
 * @param {(response: Object) => void} options.applyResponse
 * @param {() => boolean} [options.checkAuth]
 * @param {() => void} [options.onUnauthenticated]
 * @param {() => Promise<void>} [options.afterEmpty]
 * @param {number} [options.debounceMs=300] 设为 0 或负数则立即请求（仍保留去重）
 */
/**
 * 组合式函数 - 防抖分页请求：避免频繁 API 调用
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useDebouncedPaginatedFetch({
  loading,
  pagination,
  buildParams,
  fetchPage,
  applyResponse,
  checkAuth,
  onUnauthenticated,
  afterEmpty,
  debounceMs = 300
}) {
  let timer = null;
  let currentPromise = null;
  let currentParamsKey = null;

  const executeFetch = async (paramsKey, params) => {
    currentParamsKey = paramsKey;

    const requestPromise = (async () => {
      let response;
      try {
        loading.value = true;

        if (checkAuth && !checkAuth()) {
          onUnauthenticated?.();
          return;
        }

        response = await fetchPage(params);
        applyResponse(response);
      } catch (error) {
        if (error.response?.status === 401) {
          return;
        }
        if (!isErrorHandled(error)) {
          ElMessage.error(extractErrorMessage(error));
        }
      } finally {
        loading.value = false;
        if (currentParamsKey === paramsKey) {
          currentPromise = null;
          currentParamsKey = null;
        }
      }

      // afterEmpty 可能在回调内触发二次查询（如自动扩大日期范围），须在 loading 复位后执行
      if (afterEmpty && response !== undefined) {
        await afterEmpty(response);
      }
    })();

    currentPromise = requestPromise;
    await requestPromise;
  };

  const runFetch = async () => {
    if (loading.value) {
      return;
    }

    const params = buildParams();
    const paramsKey = JSON.stringify(params);

    if (currentPromise && currentParamsKey === paramsKey) {
      try {
        await currentPromise;
      } catch {
        /* 由进行中的请求处理错误 */
      }
      return;
    }

    if (timer) {
      clearTimeout(timer);
      timer = null;
    }

    if (debounceMs <= 0) {
      await executeFetch(paramsKey, params);
      return;
    }

    timer = setTimeout(() => {
      executeFetch(paramsKey, params);
    }, debounceMs);
  };

  const cancel = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  };

  return { runFetch, cancel };
}
