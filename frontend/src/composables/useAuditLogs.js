/**
 * 组合式函数 - 审计日志列表查询
 * @file composables/useAuditLogs.js
 */
import { reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { getAuditLogs, getAuditLog, getAuditLogStats, clearAllAuditLogs } from '../api/audit-log';
import { getCurrentMonthRange } from '../utils/thirdPartyReportFormat';

/**
 * 审计日志列表、统计与分页。
 */
/**
 * 组合式函数 - 审计日志列表查询
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useAuditLogs(authStore, router) {
  // logs 响应式状态
  const logs = ref([]);
  const loading = ref(false);
  // 统计数据
  const stats = ref(null);
  const isInitializing = ref(true);
  // detailDialogVisible 响应式状态
  const detailDialogVisible = ref(false);
  const currentLog = ref(null);

  // 分页状态 { page, pageSize/page_size, total }
  const pagination = reactive({
    page: 1,
    pageSize: 10,
    total: 0,
  });

  // 筛选表单字段
  const searchForm = reactive({
    username: '',
    action_type: '',
    resource_type: '',
    ip_address: '',
    success: null,
  });

  // dateRange 响应式状态
  const dateRange = ref(getCurrentMonthRange());

  const fetchStats = async (options = {}) => {
    try {
      const params = {};
      if (dateRange.value?.length === 2) {
        params.start_date = dateRange.value[0];
        params.end_date = dateRange.value[1];
      }
      if (options.forceRefresh) {
        params.force_refresh = true;
      }
      stats.value = await getAuditLogStats(params);
    } catch {
      // 静默失败
    }
  };

  const fetchLogs = async () => {
    try {
      loading.value = true;
      if (!authStore.isAuthenticated) {
        ElMessage.warning('登录已过期，请重新登录');
        router.push('/login').catch(() => {
          window.location.href = '/login';
        });
        return;
      }
      const params = {
        page: pagination.page,
        page_size: pagination.pageSize,
        ...(searchForm.username && { username: searchForm.username }),
        ...(searchForm.action_type && { action_type: searchForm.action_type }),
        ...(searchForm.resource_type && { resource_type: searchForm.resource_type }),
        ...(searchForm.ip_address && { ip_address: searchForm.ip_address }),
        ...(searchForm.success !== null &&
          searchForm.success !== '' && { success: searchForm.success }),
        ...(dateRange.value?.length === 2 && {
          start_date: dateRange.value[0],
          end_date: dateRange.value[1],
        }),
      };
      const response = await getAuditLogs(params);
      logs.value = response.data || [];
      pagination.total = response.total || 0;
      await fetchStats();
    } catch {
      // 全局拦截器处理
    } finally {
      loading.value = false;
    }
  };

  const resetFilter = () => {
    searchForm.username = '';
    searchForm.action_type = '';
    searchForm.resource_type = '';
    searchForm.ip_address = '';
    searchForm.success = null;
    dateRange.value = getCurrentMonthRange();
    pagination.page = 1;
    fetchLogs();
  };

  const handleViewDetail = async (log) => {
    try {
      currentLog.value = await getAuditLog(log.id);
      detailDialogVisible.value = true;
    } catch {
      // 全局拦截器处理
    }
  };

  const bindPaginationWatch = () => {
    watch(
      () => [pagination.page, pagination.pageSize],
      ([newPage, newSize], [oldPage, oldSize]) => {
        if (isInitializing.value) return;
        if (newPage !== oldPage && newSize === oldSize) {
          fetchLogs();
        } else if (newSize !== oldSize) {
          if (pagination.page !== 1) pagination.page = 1;
          else fetchLogs();
        }
      },
      { flush: 'post' },
    );
  };

  const finishInitializing = () => {
    isInitializing.value = false;
  };

  const clearingAll = ref(false);

  /**
   * 清空全部操作日志（调用方负责二次确认）。
   */
  const clearAllLogs = async () => {
    try {
      clearingAll.value = true;
      const result = await clearAllAuditLogs();
      logs.value = [];
      pagination.total = 0;
      pagination.page = 1;
      detailDialogVisible.value = false;
      currentLog.value = null;
      await fetchStats({ forceRefresh: true });
      return result;
    } finally {
      clearingAll.value = false;
    }
  };

  return {
    logs,
    loading,
    clearingAll,
    stats,
    pagination,
    searchForm,
    dateRange,
    detailDialogVisible,
    currentLog,
    fetchLogs,
    resetFilter,
    handleViewDetail,
    clearAllLogs,
    bindPaginationWatch,
    finishInitializing,
    getCurrentMonthRange,
  };
}
