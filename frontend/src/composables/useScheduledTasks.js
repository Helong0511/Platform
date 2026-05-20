import { computed, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { getScheduledTasks } from '../api/scheduled-task';
import { extractErrorMessage, isErrorHandled } from '../utils/api';

const FETCH_DEBOUNCE_MS = 2000;

/**
 * 定时任务列表、筛选、防抖拉取与自动刷新生命周期。
 */
export function useScheduledTasks() {
  const loading = ref(false);
  const tasks = ref([]);
  const searchForm = reactive({
    task_name: '',
    is_active: null,
    is_running: null,
  });
  const pagination = reactive({
    page: 1,
    pageSize: 10,
    total: 0,
  });

  const abortController = ref(null);
  const fetchDebounceTimer = ref(null);
  const refreshTimer = ref(null);
  const visibilityHandler = ref(null);
  const isInitializing = ref(true);

  const stats = computed(() => {
    if (tasks.value.length === 0) return null;
    return {
      total: pagination.total,
      active: tasks.value.filter((t) => t.is_active).length,
      running: tasks.value.filter((t) => t.is_running).length,
      error: tasks.value.filter((t) => t.error_count > 0).length,
    };
  });

  const fetchTasks = async (immediate = false) => {
    if (loading.value && !immediate) return;

    if (fetchDebounceTimer.value) {
      clearTimeout(fetchDebounceTimer.value);
      fetchDebounceTimer.value = null;
    }
    if (!immediate) {
      fetchDebounceTimer.value = setTimeout(() => fetchTasks(true), FETCH_DEBOUNCE_MS);
      return;
    }

    loading.value = true;
    if (abortController.value) {
      abortController.value.abort();
    }
    abortController.value = new AbortController();
    const currentController = abortController.value;

    try {
      const params = {
        page: pagination.page,
        page_size: pagination.pageSize,
        ...(searchForm.task_name && { task_name: searchForm.task_name }),
        ...(searchForm.is_active !== null &&
          searchForm.is_active !== '' && { is_active: searchForm.is_active }),
        ...(searchForm.is_running !== null &&
          searchForm.is_running !== '' && { is_running: searchForm.is_running }),
      };
      const response = await getScheduledTasks(params);
      if (currentController.signal.aborted) return;
      tasks.value = response.data || [];
      pagination.total = response.total || 0;
    } catch (error) {
      if (error.name === 'AbortError' || error.name === 'CanceledError') return;
      if (error.response?.status === 401) {
        if (!currentController.signal.aborted) loading.value = false;
        return;
      }
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    } finally {
      if (!currentController.signal.aborted) {
        loading.value = false;
      }
    }
  };

  const resetFilter = () => {
    searchForm.task_name = '';
    searchForm.is_active = null;
    searchForm.is_running = null;
    pagination.page = 1;
    fetchTasks(true);
  };

  const bindPaginationWatch = () => {
    watch(
      () => [pagination.page, pagination.pageSize],
      ([newPage, newSize], [oldPage, oldSize]) => {
        if (isInitializing.value) return;
        if (newPage !== oldPage && newSize === oldSize) {
          fetchTasks(true);
        } else if (newSize !== oldSize) {
          if (pagination.page !== 1) pagination.page = 1;
          else fetchTasks(true);
        }
      },
      { flush: 'post' },
    );
  };

  const cleanup = () => {
    if (abortController.value) {
      abortController.value.abort();
      abortController.value = null;
    }
    if (refreshTimer.value) {
      clearInterval(refreshTimer.value);
      refreshTimer.value = null;
    }
    if (fetchDebounceTimer.value) {
      clearTimeout(fetchDebounceTimer.value);
      fetchDebounceTimer.value = null;
    }
    if (visibilityHandler.value) {
      document.removeEventListener('visibilitychange', visibilityHandler.value);
      visibilityHandler.value = null;
    }
    loading.value = false;
  };

  const startAutoRefresh = () => {
    if (refreshTimer.value) clearInterval(refreshTimer.value);
    refreshTimer.value = setInterval(() => {
      if (!document.hidden && !loading.value) {
        fetchTasks();
      }
    }, 60000);
  };

  const stopAutoRefresh = () => {
    if (refreshTimer.value) {
      clearInterval(refreshTimer.value);
      refreshTimer.value = null;
    }
  };

  const setupAutoRefresh = () => {
    visibilityHandler.value = () => {
      if (document.hidden) stopAutoRefresh();
      else startAutoRefresh();
    };
    document.addEventListener('visibilitychange', visibilityHandler.value);
    startAutoRefresh();
  };

  const finishInitializing = () => {
    isInitializing.value = false;
  };

  return {
    loading,
    tasks,
    searchForm,
    pagination,
    stats,
    fetchTasks,
    resetFilter,
    bindPaginationWatch,
    cleanup,
    setupAutoRefresh,
    finishInitializing,
  };
}
