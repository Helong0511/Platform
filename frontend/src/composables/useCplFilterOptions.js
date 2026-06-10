/**
 * CPL 管理页通用筛选下拉：广告主、渠道、Offer
 * @file composables/useCplFilterOptions.js
 */
import { ref } from 'vue';
import { getAdvertisers } from '../api/advertiser';
import { getPublishers } from '../api/publisher';
import { getOffers } from '../api/offer';
import { logger } from '../utils/logger';

/**
 * @param {Object} [options]
 * @param {boolean} [options.activeOffersOnly=false] - Offer 是否仅加载激活项
 */
export function useCplFilterOptions(options = {}) {
  const { activeOffersOnly = false } = options;

  const advertiserList = ref([]);
  const publisherList = ref([]);
  const offerList = ref([]);

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

  const loadOffers = async () => {
    try {
      const params = { page: 1, page_size: 100 };
      if (activeOffersOnly) {
        params.is_active = true;
      }
      const response = await getOffers(params);
      offerList.value = (response.data || []).slice().sort((a, b) => a.id - b.id);
    } catch (error) {
      logger.error('加载Offer列表失败:', error);
    }
  };

  const loadAdvertiserPublisher = () =>
    Promise.all([loadAdvertisers(), loadPublishers()]);

  const loadAll = () =>
    Promise.all([loadAdvertisers(), loadPublishers(), loadOffers()]);

  return {
    advertiserList,
    publisherList,
    offerList,
    loadAdvertisers,
    loadPublishers,
    loadOffers,
    loadAdvertiserPublisher,
    loadAll,
  };
}
