/**
 * 防抖 + 请求去重的分页列表拉取
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
      try {
        loading.value = true;

        if (checkAuth && !checkAuth()) {
          onUnauthenticated?.();
          return;
        }

        const response = await fetchPage(params);
        applyResponse(response);

        if (afterEmpty) {
          await afterEmpty(response);
        }
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
