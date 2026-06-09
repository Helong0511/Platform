/**
 * 组合式函数 - Offer 详情面板：关联数据展示
 * @file composables/useOfferDetail.js
 */
import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import { getOffer } from '../api/offer';
import { getCaps } from '../api/cap';
import { getDiscounts } from '../api/discount';
import {
  buildPublisherShortLink,
  buildPublisherTracklinkTemplate,
  getClientPublisherCap,
  getClientPublisherPO,
  getClientPublisherTracklinkSync,
  getRowClientPublisherCap,
  getRowClientPublisherPO,
  getRowClientPublisherTracklink,
} from '../utils/offerTracklink';
import { logger } from '../utils/logger';

/**
 * Offer 详情弹窗、关联 Cap/扣量、渠道短链展示。
 */
/**
 * 组合式函数 - Offer 详情面板：关联数据展示
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useOfferDetail({ authStore, isAdmin, currentClientId }) {
  // detailDialogVisible 响应式状态
  const detailDialogVisible = ref(false);
  const detailLoading = ref(false);
  // activeTab 响应式状态
  const activeTab = ref('basic');
  const currentOffer = ref(null);
  // relatedCaps 响应式状态
  const relatedCaps = ref([]);
  const relatedDiscounts = ref([]);
  // capsLoading 响应式状态
  const capsLoading = ref(false);
  const discountsLoading = ref(false);
  // publisherShortLinks 响应式状态
  const publisherShortLinks = ref({});
  const creatingShortLinks = ref({});
  // clientPublisherTracklink 响应式状态
  const clientPublisherTracklink = ref(null);
  const loadingClientTracklink = ref(false);

  const loadRelatedCaps = async (offerId) => {
    capsLoading.value = true;
    try {
      const response = await getCaps({ page: 1, page_size: 100, offer_id: offerId });
      relatedCaps.value = response.data || [];
    } catch (error) {
      logger.error('加载Cap配置失败:', error);
    } finally {
      capsLoading.value = false;
    }
  };

  const loadRelatedDiscounts = async (offerId) => {
    discountsLoading.value = true;
    try {
      const response = await getDiscounts({ page: 1, page_size: 100, offer_id: offerId });
      relatedDiscounts.value = response.data || [];
    } catch (error) {
      logger.error('加载扣量配置失败:', error);
    } finally {
      discountsLoading.value = false;
    }
  };

  const resolveClientIdForDetail = async () => {
    let clientId = currentClientId.value;
    if (!clientId && !isAdmin.value && authStore.userInfo) {
      if (authStore.userInfo.client?.id) {
        clientId = authStore.userInfo.client.id;
      } else if (authStore.userInfo.role === 'client') {
        try {
          await authStore.fetchUserInfo();
          clientId = authStore.userInfo?.client?.id;
        } catch (error) {
          logger.error('刷新用户信息失败:', error);
        }
      }
    }
    return clientId;
  };

  const handleViewDetails = async (row) => {
    detailDialogVisible.value = true;
    activeTab.value = 'basic';
    detailLoading.value = true;
    publisherShortLinks.value = {};
    creatingShortLinks.value = {};
    try {
      currentOffer.value = await getOffer(row.id);
      if (!currentOffer.value) {
        ElMessage.error('获取详情失败');
        detailDialogVisible.value = false;
        return;
      }
      const clientId = await resolveClientIdForDetail();
      if (!isAdmin.value && clientId) {
        loadingClientTracklink.value = true;
        clientPublisherTracklink.value = null;
        try {
          clientPublisherTracklink.value = getClientPublisherTracklinkSync(
            currentOffer.value,
            clientId,
          );
        } catch (error) {
          logger.error('获取客户Tracklink失败:', error);
        } finally {
          loadingClientTracklink.value = false;
        }
      } else {
        clientPublisherTracklink.value = null;
      }
      const loadPromises = [loadRelatedCaps(row.id)];
      if (isAdmin.value) {
        loadPromises.push(loadRelatedDiscounts(row.id));
      }
      await Promise.all(loadPromises);
    } catch (error) {
      logger.error('获取Offer详情失败:', error);
      ElMessage.error('获取详情失败');
      detailDialogVisible.value = false;
    } finally {
      detailLoading.value = false;
    }
  };

  const handleDetailDialogClose = () => {
    currentOffer.value = null;
    relatedCaps.value = [];
    relatedDiscounts.value = [];
    publisherShortLinks.value = {};
    creatingShortLinks.value = {};
    clientPublisherTracklink.value = null;
    loadingClientTracklink.value = false;
    activeTab.value = 'basic';
  };

  const getPublisherTracklink = (publisherId) =>
    buildPublisherTracklinkTemplate(currentOffer.value, publisherId);

  const getPublisherShortLink = (publisherId) =>
    buildPublisherShortLink(currentOffer.value, publisherId);

  const createPublisherShortLink = async (publisherId) => {
    if (!currentOffer.value?.downstream_tracklink) {
      ElMessage.warning('Offer还没有主短链接，请先保存Offer以生成主短链接');
      return;
    }
    const channelShortLink = getPublisherShortLink(publisherId);
    if (channelShortLink) {
      publisherShortLinks.value[publisherId] = channelShortLink;
      ElMessage.success('渠道短链接已生成（主短链接 + 参数）');
    } else {
      ElMessage.warning('无法生成渠道短链接');
    }
  };

  return {
    detailDialogVisible,
    detailLoading,
    activeTab,
    currentOffer,
    relatedCaps,
    relatedDiscounts,
    capsLoading,
    discountsLoading,
    publisherShortLinks,
    creatingShortLinks,
    clientPublisherTracklink,
    loadingClientTracklink,
    handleViewDetails,
    handleDetailDialogClose,
    loadRelatedCaps,
    loadRelatedDiscounts,
    getPublisherTracklink,
    getPublisherShortLink,
    createPublisherShortLink,
    getClientPublisherPO: () => getClientPublisherPO(currentOffer.value, currentClientId.value),
    getClientPublisherCap: () => getClientPublisherCap(currentOffer.value, currentClientId.value),
    getRowClientPublisherPO: (row) => getRowClientPublisherPO(row, currentClientId.value),
    getRowClientPublisherCap: (row) => getRowClientPublisherCap(row, currentClientId.value),
    getRowClientPublisherTracklink: (row) =>
      getRowClientPublisherTracklink(row, currentClientId.value),
  };
}
