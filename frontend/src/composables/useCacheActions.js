import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { logger } from '../utils/logger';

/**
 * 缓存查看、刷新、清除与导出（演示逻辑）。
 * @param {{ removeByKey: (key: string) => void, clearAll: () => void, refreshCacheList: () => void }} deps
 */
export function useCacheActions({ removeByKey, clearAll, refreshCacheList }) {
  const clearingAll = ref(false);
  const cacheDetailVisible = ref(false);
  const currentCache = ref({});

  const viewCache = (cache) => {
    currentCache.value = { ...cache };
    cacheDetailVisible.value = true;
  };

  const refreshCache = async (cache) => {
    try {
      await ElMessageBox.confirm('确定要刷新此缓存吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      });
      setTimeout(() => {
        ElMessage.success(`缓存 ${cache.key} 已刷新`);
      }, 300);
    } catch (error) {
      if (error !== 'cancel') {
        logger.error('刷新缓存失败:', error);
      }
    }
  };

  const clearCache = async (cache) => {
    try {
      await ElMessageBox.confirm('确定要清除此缓存吗？', '警告', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      });
      removeByKey(cache.key);
      ElMessage.success(`缓存 ${cache.key} 已清除`);
    } catch (error) {
      if (error !== 'cancel') {
        logger.error('清除缓存失败:', error);
      }
    }
  };

  const clearAllCache = async () => {
    try {
      await ElMessageBox.confirm(
        '确定要清除所有缓存吗？此操作不可恢复！',
        '危险',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'danger',
        },
      );
      clearingAll.value = true;
      setTimeout(() => {
        clearAll();
        ElMessage.success('所有缓存已清除');
        clearingAll.value = false;
      }, 500);
    } catch (error) {
      if (error !== 'cancel') {
        logger.error('清除全部缓存失败:', error);
      }
      clearingAll.value = false;
    }
  };

  const exportCacheStats = () => {
    setTimeout(() => {
      ElMessage.success('缓存统计已导出（演示）');
    }, 300);
  };

  return {
    clearingAll,
    cacheDetailVisible,
    currentCache,
    viewCache,
    refreshCache,
    clearCache,
    clearAllCache,
    exportCacheStats,
  };
}
