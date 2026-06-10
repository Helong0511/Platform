/**
 * 用户管理页初始化：列设置加载 + 列表/统计顺序拉取（含超时保护）
 * @file composables/useUserManagementInit.js
 */
import { nextTick, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { extractErrorMessage, isErrorHandled } from '../utils/api';

const INIT_TIMEOUT_MS = 20000;
const STATS_DELAY_MS = 200;

/**
 * @param {Object} options
 * @param {Function} options.loadColumnVisibility
 * @param {Function} options.fetchUsers
 * @param {Function} options.fetchStats
 * @param {import('vue').Ref<boolean>} options.loading
 * @param {import('vue').Ref<boolean>} options.isInitializing
 */
export function useUserManagementInit({
  loadColumnVisibility,
  fetchUsers,
  fetchStats,
  loading,
  isInitializing,
}) {
  const initError = ref(null);

  onMounted(async () => {
    loadColumnVisibility();
    await nextTick();

    setTimeout(async () => {
      try {
        const timeoutPromise = new Promise((_, reject) => {
          setTimeout(() => {
            reject(new Error('页面加载超时，请检查网络连接或刷新页面'));
          }, INIT_TIMEOUT_MS);
        });

        await Promise.race([
          (async () => {
            await fetchUsers(true);
            await new Promise((resolve) => setTimeout(resolve, STATS_DELAY_MS));
            await fetchStats();
          })(),
          timeoutPromise,
        ]);
      } catch (error) {
        initError.value = error;
        if (error.message?.includes('超时')) {
          ElMessage.error(error.message);
          loading.value = false;
        } else if (error.response?.status === 401) {
          loading.value = false;
        } else if (!isErrorHandled(error)) {
          ElMessage.error(`页面初始化失败: ${extractErrorMessage(error)}`);
          loading.value = false;
        }
      } finally {
        await nextTick();
        isInitializing.value = false;
      }
    }, 0);
  });

  return { initError };
}
