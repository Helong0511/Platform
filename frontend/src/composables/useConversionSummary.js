/**
 * 组合式函数 - 转化总览：维度筛选与汇总
 * @file composables/useConversionSummary.js
 */
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { getConversionSummary } from '../api/conversion-summary';
import { useCplFilterOptions } from './useCplFilterOptions';
import { logger } from '../utils/logger';
import {
  buildConversionTableSummaries,
  exportConversionStatsCsv,
  getDefaultMonthDateRange,
  getDisplayConversion,
} from '../utils/conversionSummaryFormat';

/**
 * 转化总览：筛选、级联下拉、统计加载与表格汇总/导出。
 * @param {import('vue').ComputedRef<boolean>} isAdmin
 */
/**
 * 组合式函数 - 转化总览：维度筛选与汇总
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useConversionSummary(isAdmin) {
  const router = useRouter();
  // 数据加载中
  const loading = ref(false);
  const dateRange = ref([]);
  // filterOffer 响应式状态
  const filterOffer = ref(null);
  const filterAdvertiser = ref(null);
  // 按渠道（下游）筛选
  const filterPublisher = ref(null);

  // Offer 下拉选项（无日期范围时从 API 加载，有范围时由统计数据填充）
  const {
    offerList,
    advertiserList,
    publisherList,
    loadAdvertisers,
    loadPublishers,
    loadOffers,
  } = useCplFilterOptions();

  // allAdvertisersFromStats 响应式状态
  const allAdvertisersFromStats = ref([]);
  const allOffersFromStats = ref([]);
  // allPublishersFromStats 响应式状态
  const allPublishersFromStats = ref([]);
  const offerPublisherMap = ref(new Map());

  // summaryData 响应式状态
  const summaryData = reactive({
    total_clicks: 0,
    total_conversions: 0,
    cr: 0,
    total_po: 0,
    total_po_after_discount: 0,
    total_profit: 0,
    conversion_cap: 0,
    stats_list: [],
  });

  // statsList 响应式状态
  const statsList = ref([]);

  const extractOptionsFromStats = (list) => {
    const advertiserMap = new Map();
    const offerMap = new Map();
    const publisherMap = new Map();
    const offerPubMap = new Map();

    list.forEach((stat) => {
      if (stat.advertiser_id && stat.advertiser_name && !advertiserMap.has(stat.advertiser_id)) {
        advertiserMap.set(stat.advertiser_id, {
          id: stat.advertiser_id,
          advertiser_name: stat.advertiser_name,
        });
      }
      if (stat.offer_id && stat.offer_name) {
        if (!offerMap.has(stat.offer_id)) {
          offerMap.set(stat.offer_id, {
            id: stat.offer_id,
            offer_name: stat.offer_name,
            advertiser_id: stat.advertiser_id,
          });
        }
        if (stat.publisher_id) {
          if (!offerPubMap.has(stat.offer_id)) offerPubMap.set(stat.offer_id, new Set());
          offerPubMap.get(stat.offer_id).add(stat.publisher_id);
        }
      }
      if (stat.publisher_id && stat.publisher_name && !publisherMap.has(stat.publisher_id)) {
        publisherMap.set(stat.publisher_id, {
          id: stat.publisher_id,
          publisher_name: stat.publisher_name,
        });
      }
    });

    allAdvertisersFromStats.value = Array.from(advertiserMap.values());
    allOffersFromStats.value = Array.from(offerMap.values());
    allPublishersFromStats.value = Array.from(publisherMap.values());
    offerPublisherMap.value = offerPubMap;
    updateFilterLists();
  };

  const updateFilterLists = () => {
    if (dateRange.value?.length === 2) {
      if (isAdmin.value) {
        advertiserList.value = allAdvertisersFromStats.value.slice().sort((a, b) => a.id - b.id);
        if (
          filterAdvertiser.value &&
          !advertiserList.value.find((a) => a.id === filterAdvertiser.value)
        ) {
          filterAdvertiser.value = null;
        }
      }

      let filteredOffers = allOffersFromStats.value;
      if (filterAdvertiser.value) {
        filteredOffers = filteredOffers.filter((o) => o.advertiser_id === filterAdvertiser.value);
      }
      offerList.value = filteredOffers.slice().sort((a, b) => a.id - b.id);
      if (filterOffer.value && !offerList.value.find((o) => o.id === filterOffer.value)) {
        filterOffer.value = null;
      }

      let filteredPublishers = allPublishersFromStats.value;
      if (filterOffer.value) {
        const publisherIds = offerPublisherMap.value.get(filterOffer.value);
        filteredPublishers =
          publisherIds?.size > 0
            ? allPublishersFromStats.value.filter((pub) => publisherIds.has(pub.id))
            : [];
      }
      publisherList.value = filteredPublishers.slice().sort((a, b) => a.id - b.id);
      if (
        filterPublisher.value &&
        !publisherList.value.find((p) => p.id === filterPublisher.value)
      ) {
        filterPublisher.value = null;
      }
    } else {
      if (isAdmin.value) loadAdvertisers();
      loadOffers();
      loadPublishers();
    }
  };

  const loadData = async (shouldExtractOptions = false) => {
    loading.value = true;
    try {
      const params = {
        start_date: dateRange.value?.[0] || undefined,
        end_date: dateRange.value?.[1] || undefined,
        offer_id: filterOffer.value || undefined,
        advertiser_id: filterAdvertiser.value || undefined,
        publisher_id: filterPublisher.value || undefined,
      };

      if (shouldExtractOptions && dateRange.value?.length === 2) {
        const fullResponse = await getConversionSummary({
          start_date: dateRange.value[0],
          end_date: dateRange.value[1],
        });
        // getConversionSummary 使用 returnDataOnly，直接返回统计对象
        if (fullResponse?.stats_list) {
          extractOptionsFromStats(fullResponse.stats_list);
        }
      }

      const response = await getConversionSummary(params);
      if (response) {
        Object.assign(summaryData, response);
        if (
          summaryData.total_profit === 0 &&
          summaryData.total_po > 0 &&
          summaryData.total_po_after_discount > 0
        ) {
          summaryData.total_profit = summaryData.total_po - summaryData.total_po_after_discount;
        }
        statsList.value = response.stats_list || [];
      }
    } catch (error) {
      logger.error('获取统计数据失败:', error);
      ElMessage.error('获取数据失败');
    } finally {
      loading.value = false;
    }
  };

  const handleDateChange = () => {
    filterAdvertiser.value = null;
    filterOffer.value = null;
    filterPublisher.value = null;
    if (dateRange.value?.length === 2) {
      loadData(true);
    } else {
      updateFilterLists();
      loadData(false);
    }
  };

  const handleAdvertiserChange = () => {
    filterOffer.value = null;
    filterPublisher.value = null;
    updateFilterLists();
    loadData(false);
  };

  const handleOfferChange = () => {
    filterPublisher.value = null;
    updateFilterLists();
    loadData(false);
  };

  const handlePublisherChange = () => {
    loadData(false);
  };

  const handleSearch = () => {
    loadData(false);
  };

  const handleReset = () => {
    dateRange.value = getDefaultMonthDateRange();
    filterOffer.value = null;
    filterAdvertiser.value = null;
    filterPublisher.value = null;
    loadData(true);
  };

  const handleOfferClick = (offerId) => {
    if (!offerId) return;
    const route = router.resolve({ name: 'OfferManagement', query: { offer_id: offerId } });
    window.open(route.href, '_blank');
  };

  const exportToExcel = () => exportConversionStatsCsv(statsList.value, isAdmin.value);

  const getSummaries = (param) =>
    buildConversionTableSummaries(param, summaryData, isAdmin.value);

  const displayConversion = (conversions, cap) =>
    getDisplayConversion(conversions, cap, isAdmin.value);

  const initPage = () => {
    dateRange.value = getDefaultMonthDateRange();
    loadData(true);
  };

  return {
    loading,
    dateRange,
    filterOffer,
    filterAdvertiser,
    filterPublisher,
    offerList,
    advertiserList,
    publisherList,
    summaryData,
    statsList,
    handleDateChange,
    handleAdvertiserChange,
    handleOfferChange,
    handlePublisherChange,
    handleSearch,
    handleReset,
    handleOfferClick,
    exportToExcel,
    getSummaries,
    displayConversion,
    initPage,
  };
}
