/**
 * 组合式函数 - Offer 列表页：筛选、分页、数据加载
 * @file composables/useOfferList.js
 */
import { nextTick, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { getOffers } from '../api/offer';
import { useCplFilterOptions } from './useCplFilterOptions';
import { isErrorHandled } from '../utils/api';
import { logger } from '../utils/logger';

function fixSelectDisplayLater() {
  nextTick(() => {
    setTimeout(() => {
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100);
  });
}

export function useOfferList() {
  const loading = ref(false);
  const searchKeyword = ref('');
  const filterAdvertiser = ref(null);
  const filterStatus = ref(null);
  const filterActive = ref(null);
  const filterPublisher = ref(null);

  const pagination = reactive({
    page: 1,
    pageSize: 20,
    total: 0,
  });

  const tableData = ref([]);
  let loadRequestId = 0;

  const {
    advertiserList,
    publisherList,
    loadAdvertiserPublisher,
    loadAdvertisers,
    loadPublishers,
  } = useCplFilterOptions();

  const loadData = async () => {
    const requestId = ++loadRequestId;
    loading.value = true;
    try {
      const params = {
        page: pagination.page,
        page_size: Math.min(pagination.pageSize, 100),
        search: searchKeyword.value || undefined,
        advertiser_id: filterAdvertiser.value || undefined,
        publisher_id: filterPublisher.value || undefined,
        status: filterStatus.value || undefined,
        is_active: filterActive.value !== null ? filterActive.value : undefined,
      };
      const response = await getOffers(params);
      if (requestId !== loadRequestId) {
        return;
      }
      tableData.value = response.data || [];
      pagination.total = response.total || 0;
      fixSelectDisplayLater();
    } catch (error) {
      logger.error('获取Offer列表失败:', error);
      if (!isErrorHandled(error)) {
        ElMessage.error('获取数据失败');
      }
    } finally {
      if (requestId === loadRequestId) {
        loading.value = false;
      }
    }
  };

  const handleSearch = () => {
    pagination.page = 1;
    loadData();
  };

  const handleReset = () => {
    searchKeyword.value = '';
    filterAdvertiser.value = null;
    filterPublisher.value = null;
    filterStatus.value = null;
    filterActive.value = null;
    pagination.page = 1;
    loadData();
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

  const initPage = async () => {
    await loadAdvertiserPublisher();
    await loadData();
  };

  return {
    loading,
    searchKeyword,
    filterAdvertiser,
    filterStatus,
    filterActive,
    filterPublisher,
    pagination,
    tableData,
    advertiserList,
    publisherList,
    loadAdvertisers,
    loadPublishers,
    loadAdvertiserPublisher,
    loadData,
    handleSearch,
    handleReset,
    handleSizeChange,
    handlePageChange,
    initPage,
  };
}
