/**
 * 组合式函数 - 缓存操作：删除单条/批量清理
 * @file composables/useCacheActions.js
 */
import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  clearAllCacheEntries,
  deleteCacheEntry,
  getCacheEntry,
} from '../api/cache';
import { logger } from '../utils/logger';

/**
 * 缓存查看、刷新、清除（对接后端 API）。
 * @param {{ removeByKey: (key: string) => void, clearAll: () => void, refreshCacheList: () => Promise<void> }} deps
 */
/**
 * 组合式函数 - 缓存操作：删除单条/批量清理
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useCacheActions({ removeByKey, clearAll, refreshCacheList }) {
  // clearingAll 响应式状态
  const clearingAll = ref(false);
  const cacheDetailVisible = ref(false);
  // currentCache 响应式状态
  const currentCache = ref({});

  const viewCache = async (cache) => {
    try {
      const res = await getCacheEntry(cache.key);
      const data = res?.data ?? res;
      currentCache.value = { ...cache, ...data };
      cacheDetailVisible.value = true;
    } catch (error) {
      logger.error('加载缓存详情失败:', error);
      ElMessage.error(error?.message || '加载详情失败');
    }
  };

  const refreshCache = async () => {
    await refreshCacheList();
  };

  const clearCache = async (cache) => {
    if (cache.protected) {
      ElMessage.warning('该缓存键受保护，不可删除');
      return;
    }
    try {
      await ElMessageBox.confirm(`确定要清除缓存 ${cache.key} 吗？`, '警告', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      });
      await deleteCacheEntry(cache.key);
      removeByKey(cache.key);
      ElMessage.success(`缓存 ${cache.key} 已清除`);
    } catch (error) {
      if (error !== 'cancel') {
        logger.error('清除缓存失败:', error);
        ElMessage.error(error?.message || '清除失败');
      }
    }
  };

  const clearAllCache = async () => {
    try {
      await ElMessageBox.confirm(
        '确定要清除所有非受保护缓存吗？CSRF/限流等系统键将保留。',
        '危险',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'danger',
        },
      );
      clearingAll.value = true;
      const res = await clearAllCacheEntries();
      const deleted = res?.data?.deleted ?? res?.deleted ?? 0;
      clearAll();
      ElMessage.success(`已清除 ${deleted} 个缓存键`);
      await refreshCacheList();
    } catch (error) {
      if (error !== 'cancel') {
        logger.error('清除全部缓存失败:', error);
        ElMessage.error(error?.message || '清除失败');
      }
    } finally {
      clearingAll.value = false;
    }
  };

  const exportCacheStats = async () => {
    try {
      const { getCacheStats } = await import('../api/cache');
      const res = await getCacheStats();
      const data = res?.data ?? res;
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `cache-stats-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      ElMessage.success('缓存统计已导出');
    } catch (error) {
      logger.error('导出缓存统计失败:', error);
      ElMessage.error(error?.message || '导出失败');
    }
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
