import { ref, reactive, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { getThirdPartyReports, getThirdPartyReportStats } from '../api/third-party-report';
import { getCurrentMonthRange } from '../utils/thirdPartyReportFormat';
import { logger } from '../utils/logger';

/**
 * 第三方上报日志列表、统计与分页。
 */
export function useThirdPartyReports(authStore, router) {
  const logs = ref([]);
  const loading = ref(false);
  const stats = ref(null);
  const pagination = reactive({
    page: 1,
    pageSize: 10,
    total: 0,
  });
  const searchForm = reactive({
    source: '',
    adsid: '',
    event: '',
    status: '',
  });
  const dateRange = ref(getCurrentMonthRange());

  const fetchStats = async () => {
    try {
      const params = {};
      if (dateRange.value?.length === 2) {
        params.start_date = dateRange.value[0];
        params.end_date = dateRange.value[1];
      }
      stats.value = await getThirdPartyReportStats(params);
    } catch (error) {
      logger.error('获取第三方上报统计失败:', error);
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
        ...(searchForm.source && { source: searchForm.source }),
        ...(searchForm.adsid && { adsid: searchForm.adsid }),
        ...(searchForm.event && { event: searchForm.event }),
        ...(searchForm.status && { status: searchForm.status }),
        ...(dateRange.value?.length === 2 && {
          start_date: dateRange.value[0],
          end_date: dateRange.value[1],
        }),
      };
      const response = await getThirdPartyReports(params);
      logs.value = response.data || [];
      pagination.total = response.total || 0;
      await fetchStats();
    } catch (error) {
      logger.error('获取第三方上报日志失败:', error);
    } finally {
      loading.value = false;
    }
  };

  const resetFilter = () => {
    searchForm.source = '';
    searchForm.adsid = '';
    searchForm.event = '';
    searchForm.status = '';
    dateRange.value = getCurrentMonthRange();
    pagination.page = 1;
    fetchLogs();
  };

  const bindPaginationWatch = (isInitializing) => {
    watch(
      () => [pagination.page, pagination.pageSize],
      ([newPage, newSize], [oldPage, oldSize]) => {
        if (isInitializing.value) {
          return;
        }
        if (newPage !== oldPage && newSize === oldSize) {
          fetchLogs();
        } else if (newSize !== oldSize) {
          if (pagination.page !== 1) {
            pagination.page = 1;
          } else {
            fetchLogs();
          }
        }
      },
      { flush: 'post' },
    );
  };

  return {
    logs,
    loading,
    stats,
    pagination,
    searchForm,
    dateRange,
    fetchLogs,
    fetchStats,
    resetFilter,
    bindPaginationWatch,
    getCurrentMonthRange,
  };
}
