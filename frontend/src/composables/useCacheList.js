import { computed, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { listCacheEntries } from '../api/cache';
import { logger } from '../utils/logger';

/**
 * 缓存列表（对接 /api/v1/cache/entries）。
 */
export function useCacheList() {
  const loading = ref(false);
  const cacheList = ref([]);
  const redisAvailable = ref(true);

  const flatCacheList = computed(() => cacheList.value);

  const refreshCacheList = async () => {
    loading.value = true;
    try {
      const res = await listCacheEntries({ limit: 300 });
      const data = res?.data ?? res;
      cacheList.value = data?.items ?? [];
      redisAvailable.value = data?.redis_available !== false;
      if (!redisAvailable.value) {
        ElMessage.warning('Redis 不可用，无法加载缓存列表');
      } else {
        ElMessage.success('缓存列表已刷新');
      }
    } catch (error) {
      logger.error('刷新缓存列表失败:', error);
      ElMessage.error(error?.message || '刷新失败');
    } finally {
      loading.value = false;
    }
  };

  const removeByKey = (key) => {
    const index = cacheList.value.findIndex((item) => item.key === key);
    if (index > -1) {
      cacheList.value.splice(index, 1);
    }
  };

  const clearAll = () => {
    cacheList.value = [];
  };

  return {
    loading,
    cacheList,
    flatCacheList,
    redisAvailable,
    refreshCacheList,
    removeByKey,
    clearAll,
  };
}
