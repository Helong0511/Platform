import { reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { getClicks, getClickDetail } from '../api/clicks';
import { getOffers } from '../api/offer';
import { getPublishers } from '../api/publisher';
import { logger } from '../utils/logger';

/**
 * 短链接访问记录（Click Log）列表与筛选。
 */
export function useClickLogList() {
  const route = useRoute();
  const router = useRouter();
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
  const pagination = reactive({
    page: 1,
    pageSize: 20,
    total: 0,
  });
  const tableData = ref([]);
  const offerList = ref([]);
  const publisherList = ref([]);
  const detailDialogVisible = ref(false);
  const currentDetail = ref(null);

  let searchDebounceTimer = null;

  const loadOffers = async () => {
    try {
      const response = await getOffers({ page: 1, page_size: 100, is_active: true });
      offerList.value = (response.data || []).slice().sort((a, b) => a.id - b.id);
    } catch (error) {
      logger.error('加载Offer列表失败:', error);
      ElMessage.warning('加载Offer列表失败，筛选功能可能受限');
    }
  };

  const loadPublishers = async () => {
    try {
      const response = await getPublishers({ page: 1, page_size: 100 });
      publisherList.value = response.data || [];
    } catch (error) {
      logger.error('加载渠道列表失败:', error);
    }
  };

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

  const handleSearch = () => {
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
    loadOffers,
    loadPublishers,
    loadData,
    handleSearch,
    debouncedSearch,
    handleReset,
    handleShortCodeClick,
    showDetail,
    handleSizeChange,
    handlePageChange,
    initPage,
  };
}
