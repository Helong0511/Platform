/**
 * 组合式函数 - 定时任务列表与状态
 * @file composables/useScheduledTasks.js
 *
 * 有任务运行中时提高轮询频率，保证查询结果能及时显示「正在运行」并禁用启用开关。
 */
import { computed, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { getScheduledTasks, getTaskQueueStatus, getSchedulerStatus } from '../api/scheduled-task';
import { extractErrorMessage, isErrorHandled } from '../utils/api';
import { normalizeScheduledTaskRow } from '../utils/scheduledTaskStatus';

/** 空闲时自动刷新间隔 */
const IDLE_REFRESH_MS = 60000;
/** 存在运行中任务时的刷新间隔（便于前端及时展示「正在运行」） */
const RUNNING_REFRESH_MS = 5000;
const FETCH_DEBOUNCE_MS = 2000;

/**
 * 定时任务列表、筛选、防抖拉取与自动刷新生命周期。
 */
/**
 * 组合式函数 - 定时任务列表与状态
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useScheduledTasks() {
  // 数据加载中
  const loading = ref(false);
  const tasks = ref([]);
  /** 队列/调度器运行时诊断（与列表聚合互补） */
  const runtimeStatus = ref({
    queue: null,
    scheduler: null,
  });
  // 筛选表单字段
  const searchForm = reactive({
    task_name: '',
    is_active: null,
    is_running: null,
  });
  // 分页状态 { page, pageSize/page_size, total }
  const pagination = reactive({
    page: 1,
    pageSize: 10,
    total: 0,
  });

  // abortController 响应式状态
  const abortController = ref(null);
  const fetchDebounceTimer = ref(null);
  // refreshTimer 响应式状态
  const refreshTimer = ref(null);
  const visibilityHandler = ref(null);
  // isInitializing 响应式状态
  const isInitializing = ref(true);

  const stats = computed(() => {
    if (tasks.value.length === 0 && !runtimeStatus.value.queue) return null;
    const queue = runtimeStatus.value.queue || {};
    const scheduler = runtimeStatus.value.scheduler || {};
    return {
      total: pagination.total,
      active: tasks.value.filter((t) => t.is_active).length,
      running: tasks.value.filter((t) => t.is_running).length,
      error: tasks.value.filter((t) => t.error_count > 0).length,
      queueLength: queue.queue_length ?? null,
      queueRunning: queue.current_running ?? null,
      schedulerRunning: scheduler.scheduler_running ?? null,
      schedulerJobs: scheduler.total_jobs ?? null,
    };
  });

  const fetchRuntimeStatus = async () => {
    try {
      const [queue, scheduler] = await Promise.all([
        getTaskQueueStatus(),
        getSchedulerStatus(),
      ]);
      runtimeStatus.value = { queue: queue || null, scheduler: scheduler || null };
    } catch (error) {
      // 诊断接口失败不阻断列表；保留上次成功值
      if (!isErrorHandled(error)) {
        console.warn('获取调度器/队列状态失败', error);
      }
    }
  };

  const hasRunningTasks = computed(() => tasks.value.some((t) => t.is_running));

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
      const response = await getScheduledTasks(params, { signal: currentController.signal });
      if (currentController.signal.aborted) return;
      // 归一化布尔字段，避免 is_running 非严格 true 时开关仍可点
      tasks.value = (response.data || []).map(normalizeScheduledTaskRow);
      pagination.total = response.total || 0;
      // 并行刷新队列/调度器诊断（不阻塞列表）
      fetchRuntimeStatus();
      // 运行状态变化时调整轮询节奏
      if (!document.hidden) {
        startAutoRefresh();
      }
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
    const intervalMs = hasRunningTasks.value ? RUNNING_REFRESH_MS : IDLE_REFRESH_MS;
    refreshTimer.value = setInterval(() => {
      if (!document.hidden && !loading.value) {
        // 有运行中任务时立即拉取，保证「正在运行」与禁用启用开关及时更新
        fetchTasks(hasRunningTasks.value);
      }
    }, intervalMs);
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
    runtimeStatus,
    fetchTasks,
    resetFilter,
    bindPaginationWatch,
    cleanup,
    setupAutoRefresh,
    finishInitializing,
  };
}
