/**
 * 组合式函数 - 点击日志列表查询
 * @file composables/useClickLogList.js
 */
import { reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getClicks, getClickDetail, resendClickFacebookReport } from '../api/clicks';
import { useCplFilterOptions } from './useCplFilterOptions';
import { logger } from '../utils/logger';

/**
 * 短链接访问记录（Click Log）列表与筛选。
 */
/**
 * 组合式函数 - 点击日志列表查询
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useClickLogList() {
  const route = useRoute();
  const router = useRouter();
  // 数据加载中
  const loading = ref(false);
  const filters = reactive({
    clickId: '',
    conversionId: '',
    offer: null,
    publisher: null,
    ip: '',
    country: '',
    dateRange: [],
  });
  // 分页状态 { page, pageSize/page_size, total }
  const pagination = reactive({
    page: 1,
    pageSize: 20,
    total: 0,
  });
  // 表格当前页数据
  const tableData = ref([]);
  const {
    offerList,
    publisherList,
    loadOffers,
    loadPublishers,
  } = useCplFilterOptions({ activeOffersOnly: true });
  const detailDialogVisible = ref(false);
  // currentDetail 响应式状态
  const currentDetail = ref(null);
  const fbReportLoadingMap = ref({});

  let searchDebounceTimer = null;

  const loadData = async () => {
    loading.value = true;
    try {
      const params = {
        page: pagination.page,
        page_size: Math.min(pagination.pageSize, 100),
        click_id: filters.clickId || undefined,
        conversion_id: filters.conversionId || undefined,
        offer_id: filters.offer || undefined,
        publisher_id: filters.publisher || undefined,
        ip: filters.ip || undefined,
        country: filters.country || undefined,
        start_date: filters.dateRange?.[0] || undefined,
        end_date: filters.dateRange?.[1] || undefined,
      };
      const response = await getClicks(params);
      tableData.value = response.data || [];
      pagination.total = response.total || 0;
      if (filters.conversionId && tableData.value.length === 1) {
        await showDetail(tableData.value[0]);
      }
    } catch (error) {
      logger.error('获取短链接访问记录失败:', error);
      ElMessage.error('获取数据失败');
    } finally {
      loading.value = false;
    }
  };

  /**
   * 合并筛选条件到 composable 内 reactive filters。
   * 筛选栏 payload 不含 conversionId（仅 URL 深链使用）；合并时须显式清空，避免旧条件残留。
   */
  const patchFilters = (partial) => {
    if (!partial || typeof partial !== 'object') {
      return;
    }
    Object.assign(filters, partial);
    if (!('conversionId' in partial)) {
      filters.conversionId = '';
    }
  };

  const handleSearch = (partial) => {
    patchFilters(partial);
    pagination.page = 1;
    loadData();
  };

  const debouncedSearch = (delay = 500) => {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(handleSearch, delay);
  };

  const handleReset = () => {
    filters.clickId = '';
    filters.conversionId = '';
    filters.offer = null;
    filters.publisher = null;
    filters.ip = '';
    filters.country = '';
    filters.dateRange = [];
    pagination.page = 1;
    loadData();
  };

  const handleShortCodeClick = async (shortCode) => {
    if (!shortCode) return;
    try {
      await router.push({ name: 'ShortLinkManagement', query: { search: shortCode } });
    } catch (error) {
      logger.error('跳转到短链接管理页面失败:', error);
      ElMessage.error('跳转失败，请重试');
    }
  };

  const showDetail = async (row) => {
    if (!row?.id) {
      ElMessage.error('记录ID缺失，无法查看详情');
      return;
    }
    try {
      currentDetail.value = (await getClickDetail(row.id)) || row;
      detailDialogVisible.value = true;
    } catch (error) {
      logger.error('获取点击记录详情失败:', error);
      currentDetail.value = row;
      detailDialogVisible.value = true;
      ElMessage.warning('详情加载较慢，已显示基础信息');
    }
  };

  const reportFacebookForClick = async (row) => {
    if (!row?.id) {
      ElMessage.error('记录ID缺失，无法执行补报');
      return;
    }
    if (!row?.conversion_id) {
      ElMessage.warning('仅已转化记录支持 Facebook 补报');
      return;
    }

    try {
      await ElMessageBox.confirm(
        '确认对这条已转化点击执行 Facebook 像素补报吗？',
        '补报确认',
        {
          type: 'warning',
          confirmButtonText: '确认补报',
          cancelButtonText: '取消',
        }
      );
    } catch {
      return;
    }

    fbReportLoadingMap.value = { ...fbReportLoadingMap.value, [row.id]: true };
    try {
      const res = await resendClickFacebookReport(row.id);
      ElMessage.success(res?.message || 'Facebook 像素补报已发送');
    } catch (error) {
      logger.error('Facebook 像素补报失败:', error);
      ElMessage.error(error?.message || 'Facebook 像素补报失败');
    } finally {
      const next = { ...fbReportLoadingMap.value };
      delete next[row.id];
      fbReportLoadingMap.value = next;
    }
  };

  const handleSizeChange = (size) => {
    pagination.pageSize = size;
    pagination.page = 1;
    loadData();
  };

  const handlePageChange = (page) => {
    pagination.page = page;
    loadData();
  };

  const formatLocalDate = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  /** 根据路由 query 初始化筛选并加载列表 */
  const initPage = () => {
    const clickIdFromUrl = route.query.click_id;
    const conversionIdFromUrl = route.query.conversion_id;
    if (clickIdFromUrl) filters.clickId = String(clickIdFromUrl);
    if (conversionIdFromUrl) filters.conversionId = String(conversionIdFromUrl);
    if (!clickIdFromUrl && !conversionIdFromUrl) {
      const endDate = new Date();
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - 7);
      filters.dateRange = [formatLocalDate(startDate), formatLocalDate(endDate)];
    }
    loadData();
  };

  return {
    loading,
    filters,
    pagination,
    tableData,
    offerList,
    publisherList,
    detailDialogVisible,
    currentDetail,
    fbReportLoadingMap,
    loadOffers,
    loadPublishers,
    loadData,
    patchFilters,
    handleSearch,
    debouncedSearch,
    handleReset,
    handleShortCodeClick,
    showDetail,
    reportFacebookForClick,
    handleSizeChange,
    handlePageChange,
    initPage,
  };
}
