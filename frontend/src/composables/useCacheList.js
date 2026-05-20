import { computed, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { createMockCacheList } from '../data/mockCacheList';
import { logger } from '../utils/logger';

/**
 * 缓存列表（当前为演示数据，待对接后端缓存 API）。
 */
export function useCacheList() {
  const loading = ref(false);
  const cacheList = ref(createMockCacheList());

  const flatCacheList = computed(() => cacheList.value);

  const refreshCacheList = () => {
    loading.value = true;
    setTimeout(() => {
      try {
        cacheList.value = createMockCacheList();
        ElMessage.success('缓存列表已刷新');
      } catch (error) {
        logger.error('刷新缓存列表失败:', error);
        ElMessage.error('刷新失败');
      } finally {
        loading.value = false;
      }
    }, 500);
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
    refreshCacheList,
    removeByKey,
    clearAll,
  };
}
