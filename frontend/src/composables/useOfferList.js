/**
 * 组合式函数 - Offer 列表页：筛选、分页、数据加载
 * @file composables/useOfferList.js
 */
import { nextTick, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { getOffers } from '../api/offer';
import { getAdvertisers } from '../api/advertiser';
import { getPublishers } from '../api/publisher';
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

/**
 * 组合式函数 - Offer 列表页：筛选、分页、数据加载
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useOfferList() {
  // 数据加载中
  const loading = ref(false);
  const searchKeyword = ref('');
  // 按广告主（上游）筛选
  const filterAdvertiser = ref(null);
  const filterStatus = ref(null);
  // 按激活状态筛选
  const filterActive = ref(null);
  const filterPublisher = ref(null);

  // 分页状态 { page, pageSize/page_size, total }
  const pagination = reactive({
    page: 1,
    pageSize: 20,
    total: 0,
  });

  // 表格当前页数据
  const tableData = ref([]);
  const advertiserList = ref([]);
  // 渠道下拉选项
  const publisherList = ref([]);

  const loadAdvertisers = async () => {
    try {
      const response = await getAdvertisers({ page: 1, page_size: 100 });
      advertiserList.value = response.data || [];
    } catch (error) {
      logger.error('加载广告主列表失败:', error);
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
        search: searchKeyword.value || undefined,
        advertiser_id: filterAdvertiser.value || undefined,
        publisher_id: filterPublisher.value || undefined,
        status: filterStatus.value || undefined,
        is_active: filterActive.value !== null ? filterActive.value : undefined,
      };
      const response = await getOffers(params);
      tableData.value = response.data || [];
      pagination.total = response.total || 0;
    } catch (error) {
      logger.error('获取Offer列表失败:', error);
      ElMessage.error('获取数据失败');
    } finally {
      loading.value = false;
    }
  };

  const handleSearch = () => {
    pagination.page = 1;
    loadData();
  };

  const handleReset = () => {
    searchKeyword.value = '';
    filterAdvertiser.value = null;
    filterStatus.value = null;
    filterActive.value = null;
    filterPublisher.value = null;
    pagination.page = 1;
    loadData();
    fixSelectDisplayLater();
  };

  const handleAdvertiserChange = () => {
    fixSelectDisplayLater();
    handleSearch();
  };

  const handleStatusChange = () => {
    fixSelectDisplayLater();
    handleSearch();
  };

  const handleActiveChange = () => {
    fixSelectDisplayLater();
    handleSearch();
  };

  const handlePublisherChange = () => {
    fixSelectDisplayLater();
    handleSearch();
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
    loadData,
    handleSearch,
    handleReset,
    handleAdvertiserChange,
    handleStatusChange,
    handleActiveChange,
    handlePublisherChange,
  };
}
