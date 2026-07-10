/**
 * 组合式函数 - 短链接列表
 * @file composables/useShortLinkList.js
 */
import { reactive, ref, watch, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import { getShortLinks, getShortLinkStats, updateShortLink } from '../api/short-link';
import { getOffers } from '../api/offer';
import { getPublishers } from '../api/publisher';
import { isErrorHandled } from '../utils/api';
import { logger } from '../utils/logger';

/**
 * 短链接列表、统计、筛选与路由 search 参数联动。
 */
/**
 * 组合式函数 - 短链接列表
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useShortLinkList() {
  const route = useRoute();
  // 数据加载中
  const loading = ref(false);
  const links = ref([]);
  // Offer 下拉选项
  const offerList = ref([]);
  const channelList = ref([]);
  // 统计数据
  const stats = reactive({
    total_links: 0,
    total_clicks: 0,
    active_links: 0,
    expired_links: 0,
  });
  // filters 响应式状态
  const filters = reactive({
    search: '',
    is_active: null,
  });
  // 分页状态 { page, pageSize/page_size, total }
  const pagination = reactive({
    page: 1,
    pageSize: 20,
    total: 0,
  });

  let isApplyingSearch = false;
  let loadRequestId = 0;

  const loadData = async () => {
    const requestId = ++loadRequestId;
    loading.value = true;
    try {
      const params = {
        page: pagination.page,
        page_size: pagination.pageSize,
      };
      if (filters.search?.trim()) {
        params.search = filters.search.trim();
      }
      if (filters.is_active !== null && filters.is_active !== undefined) {
        params.is_active = filters.is_active;
      }
      const result = await getShortLinks(params);
      if (requestId !== loadRequestId) {
        return;
      }
      links.value = (result.data || []).map((link) => ({
        ...link,
        _toggleLoading: false,
      }));
      pagination.total = result.total || 0;
    } catch (error) {
      logger.error('加载短链接列表失败:', error);
      if (!isErrorHandled(error)) {
        ElMessage.error('加载数据失败，请重试');
      }
    } finally {
      if (requestId === loadRequestId) {
        loading.value = false;
      }
    }
  };

  const loadStats = async () => {
    try {
      Object.assign(stats, await getShortLinkStats());
    } catch (error) {
      logger.error('加载统计失败:', error);
    }
  };

  const refreshListAndStats = async () => {
    await loadData();
    await loadStats();
  };

  const loadOffers = async () => {
    try {
      const response = await getOffers({ page: 1, page_size: 100 });
      offerList.value = response.data || [];
    } catch (error) {
      logger.error('加载Offer列表失败:', error);
    }
  };

  const loadChannels = async () => {
    try {
      const response = await getPublishers({ page: 1, page_size: 100 });
      channelList.value = response.data || [];
    } catch (error) {
      logger.error('加载渠道列表失败:', error);
    }
  };

  const getOfferName = (offerId) => {
    if (!offerId) return null;
    return offerList.value.find((o) => o.id === offerId)?.offer_name ?? null;
  };

  const getChannelName = (channelId) => {
    if (!channelId) return null;
    return channelList.value.find((c) => c.id === channelId)?.publisher_name ?? null;
  };

  const handleSearch = () => {
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

  const handleToggleActive = async (link) => {
    if (link._toggleLoading) return;
    const originalValue = !link.is_active;
    const newValue = link.is_active;
    link._toggleLoading = true;
    try {
      await updateShortLink(link.id, { is_active: newValue });
      ElMessage.success(newValue ? '短链接已激活' : '短链接已禁用');
      await loadStats();
    } catch (error) {
      link.is_active = originalValue;
      logger.error('切换激活状态失败:', error);
    } finally {
      link._toggleLoading = false;
    }
  };

  const applySearchFromQuery = async () => {
    if (isApplyingSearch) return;
    isApplyingSearch = true;
    try {
      const searchFromQuery = route.query.search;
      if (searchFromQuery) {
        const searchValue = String(searchFromQuery).trim();
        if (!/^[a-zA-Z0-9_-]+$/.test(searchValue)) {
          logger.warn('Invalid short code format:', searchValue);
        }
        filters.search = searchValue;
        pagination.page = 1;
        await nextTick();
        await loadData();
      } else if (filters.search) {
        filters.search = '';
        pagination.page = 1;
        await nextTick();
        await loadData();
      } else if (pagination.page === 1) {
        await loadData();
      }
    } finally {
      isApplyingSearch = false;
    }
  };

  const bindRouteSearchWatch = () => {
    watch(
      () => route.query.search,
      async (newSearch, oldSearch) => {
        if (newSearch !== oldSearch) {
          await nextTick();
          await applySearchFromQuery();
        }
      },
    );
    watch(
      () => route.fullPath,
      async (newPath, oldPath) => {
        if (newPath !== oldPath && route.name === 'ShortLinkManagement') {
          await nextTick();
          await applySearchFromQuery();
        }
      },
    );
  };

  const initPage = async () => {
    loadStats();
    loadOffers();
    loadChannels();
    await nextTick();
    const searchFromQuery = route.query.search;
    if (searchFromQuery) {
      filters.search = String(searchFromQuery).trim();
      pagination.page = 1;
      await nextTick();
      await loadData();
    } else {
      await loadData();
    }
  };

  return {
    loading,
    links,
    offerList,
    channelList,
    stats,
    filters,
    pagination,
    loadData,
    loadStats,
    refreshListAndStats,
    getOfferName,
    getChannelName,
    handleSearch,
    handleSizeChange,
    handlePageChange,
    handleToggleActive,
    bindRouteSearchWatch,
    initPage,
  };
}
