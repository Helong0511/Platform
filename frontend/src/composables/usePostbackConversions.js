import { ref, reactive, watch } from 'vue';
import { getPostbackConversions, getPostbackStats } from '../api/postback';
import { getOffers } from '../api/offer';
import { getPublishers } from '../api/publisher';
import { getAdvertisers } from '../api/advertiser';
import { logger } from '../utils/logger';

/**
 * Postback 转化列表：筛选、分页、统计与下拉数据。
 */
export function usePostbackConversions() {
  const conversions = ref([]);
  const loading = ref(false);
  const stats = ref([]);
  const pagination = reactive({
    page: 1,
    pageSize: 20,
    total: 0,
  });

  const searchForm = reactive({
    platform: '',
    conversion_or_click_id: '',
    product_id: null,
    client_id: null,
    click_id: '',
    offer_id: null,
    publisher_id: null,
    advertiser_id: null,
    conversion_status: null,
    start_date: '',
    end_date: '',
  });

  const offerList = ref([]);
  const publisherList = ref([]);
  const advertiserList = ref([]);
  const dateRange = ref(null);

  const buildListParams = () => {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...searchForm,
    };
    Object.keys(params).forEach((key) => {
      if (params[key] === '' || params[key] === null || params[key] === undefined) {
        delete params[key];
      }
    });
    return params;
  };

  const fetchConversions = async () => {
    loading.value = true;
    try {
      const response = await getPostbackConversions(buildListParams());
      const conversionList = response.data || [];
      conversionList.forEach((conversion) => {
        conversion.has_notification = (conversion.notification_count || 0) > 0;
      });
      conversions.value = conversionList;
      pagination.total = response.total || 0;
    } catch (_error) {
      // 错误已由全局拦截器处理
    } finally {
      loading.value = false;
    }
  };

  const fetchStats = async () => {
    try {
      const params = {};
      if (searchForm.platform) params.platform = searchForm.platform;
      if (searchForm.start_date) params.start_date = searchForm.start_date;
      if (searchForm.end_date) params.end_date = searchForm.end_date;
      stats.value = (await getPostbackStats(params)) || [];
    } catch (_error) {
      // 错误已由全局拦截器处理
    }
  };

  const loadOffers = async () => {
    try {
      const response = await getOffers({ page: 1, page_size: 100, is_active: true });
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

  const loadAdvertisers = async () => {
    try {
      const response = await getAdvertisers({ page: 1, page_size: 100 });
      advertiserList.value = response.data || [];
    } catch (error) {
      logger.error('加载广告主列表失败:', error);
    }
  };

  const resetFilter = () => {
    searchForm.platform = '';
    searchForm.conversion_or_click_id = '';
    searchForm.product_id = null;
    searchForm.client_id = null;
    searchForm.click_id = '';
    searchForm.offer_id = null;
    searchForm.publisher_id = null;
    searchForm.advertiser_id = null;
    searchForm.conversion_status = null;
    searchForm.start_date = '';
    searchForm.end_date = '';
    dateRange.value = null;
    pagination.page = 1;
    fetchConversions();
    fetchStats();
  };

  const initFilters = () => {
    watch(dateRange, (newVal) => {
      if (newVal && newVal.length === 2) {
        searchForm.start_date = newVal[0];
        searchForm.end_date = newVal[1];
      } else {
        searchForm.start_date = '';
        searchForm.end_date = '';
      }
    });
    watch(() => pagination.page, () => fetchConversions());
    watch(() => pagination.pageSize, () => {
      pagination.page = 1;
      fetchConversions();
    });
  };

  const loadAll = async () => {
    await Promise.all([loadOffers(), loadPublishers(), loadAdvertisers()]);
    await fetchConversions();
    await fetchStats();
  };

  return {
    conversions,
    loading,
    stats,
    pagination,
    searchForm,
    offerList,
    publisherList,
    advertiserList,
    dateRange,
    fetchConversions,
    fetchStats,
    resetFilter,
    loadAll,
    initFilters,
  };
}
