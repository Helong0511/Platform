import { reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { getDiscounts, updateDiscount } from '../api/discount';
import { getOffers } from '../api/offer';
import { getPublishers } from '../api/publisher';
import { logger } from '../utils/logger';

/**
 * 扣量配置列表、筛选与行内状态切换。
 */
export function useDiscountList() {
  const loading = ref(false);
  const filterDiscountType = ref(null);
  const filterOffer = ref(null);
  const filterPublisher = ref(null);
  const filterActive = ref(null);
  const pagination = reactive({
    page: 1,
    pageSize: 20,
    total: 0,
  });
  const tableData = ref([]);
  const offerList = ref([]);
  const publisherList = ref([]);

  const loadOffers = async () => {
    try {
      const response = await getOffers({ page: 1, page_size: 100 });
      offerList.value = (response.data || []).slice().sort((a, b) => a.id - b.id);
    } catch (error) {
      logger.error('加载Offer列表失败:', error);
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
        discount_type: filterDiscountType.value || undefined,
        offer_id: filterOffer.value || undefined,
        publisher_id: filterPublisher.value || undefined,
        is_active: filterActive.value !== null ? filterActive.value : undefined,
      };
      const response = await getDiscounts(params);
      tableData.value = response.data || [];
      pagination.total = response.total || 0;
    } catch (error) {
      logger.error('获取扣量配置列表失败:', error);
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
    filterDiscountType.value = null;
    filterOffer.value = null;
    filterPublisher.value = null;
    filterActive.value = null;
    pagination.page = 1;
    loadData();
  };

  const handleStatusChange = async (row) => {
    const originalState = row.is_active;
    try {
      await updateDiscount(row.id, { is_active: row.is_active });
      loadData();
    } catch (error) {
      row.is_active = originalState;
      logger.error('更新扣量配置状态失败:', error);
      if (error.response?.status === 401) return;
      if (error.response?.status === 403 && error._handled) return;
      const errorMsg =
        error.response?.data?.detail ||
        error.response?.data?.message ||
        error.message ||
        '更新失败';
      ElMessage.error(errorMsg);
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

  const initPage = () => {
    loadOffers();
    loadPublishers();
    loadData();
  };

  return {
    loading,
    filterDiscountType,
    filterOffer,
    filterPublisher,
    filterActive,
    pagination,
    tableData,
    offerList,
    publisherList,
    loadData,
    handleSearch,
    handleReset,
    handleStatusChange,
    handleSizeChange,
    handlePageChange,
    initPage,
  };
}
