/**
 * 组合式函数 - 通用表格列显隐（localStorage 持久化）
 * @file composables/useTableColumnVisibility.js
 */
import { computed, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { logger } from '../utils/logger';

/**
 * 表格列显示偏好（localStorage），供各管理页复用。
 *
 * @param {string} storageKey localStorage 键名
 * @param {object} options
 * @param {() => Record<string, boolean>} options.getDefaultColumns 默认列可见性
 * @param {(visibility: Record<string, boolean>) => Record<string, boolean>} options.getSavableColumns 持久化字段子集
 * @param {string[]} [options.pinColumns] 加载后强制为 true 的列（如 id）
 */
/**
 * 组合式函数 - 通用表格列显隐（localStorage 持久化）
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useTableColumnVisibility(storageKey, options) {
  const { getDefaultColumns, getSavableColumns, pinColumns = [] } = options;
  // columnSettingVisible 响应式状态
  const columnSettingVisible = ref(false);
  const columnVisibility = reactive(getDefaultColumns());

  const applyPinnedColumns = () => {
    pinColumns.forEach((key) => {
      if (key in columnVisibility) {
        columnVisibility[key] = true;
      }
    });
  };

  const columnVisibilityArray = computed({
    get: () => Object.keys(columnVisibility).filter((key) => columnVisibility[key]),
    set: (value) => {
      const selected = new Set(value);
      Object.keys(columnVisibility).forEach((key) => {
        if (pinColumns.includes(key)) {
          columnVisibility[key] = true;
        } else {
          columnVisibility[key] = selected.has(key);
        }
      });
    },
  });

  const loadColumnVisibility = () => {
    try {
      Object.assign(columnVisibility, getDefaultColumns());
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          Object.assign(columnVisibility, parsed);
        }
      }
      applyPinnedColumns();
    } catch (error) {
      logger.error('加载列显示设置失败:', error);
      Object.assign(columnVisibility, getDefaultColumns());
      applyPinnedColumns();
    }
  };

  const saveColumnVisibility = () => {
    try {
      applyPinnedColumns();
      localStorage.setItem(storageKey, JSON.stringify(getSavableColumns(columnVisibility)));
      columnSettingVisible.value = false;
      ElMessage.success('列显示设置已保存');
    } catch (error) {
      logger.error('保存列显示设置失败:', error);
      ElMessage.error('保存设置失败');
    }
  };

  const resetColumnVisibility = () => {
    Object.assign(columnVisibility, getDefaultColumns());
    applyPinnedColumns();
    try {
      localStorage.removeItem(storageKey);
      ElMessage.success('已恢复默认列显示');
    } catch (error) {
      logger.error('重置列显示设置失败:', error);
    }
  };

  return {
    columnSettingVisible,
    columnVisibility,
    columnVisibilityArray,
    loadColumnVisibility,
    saveColumnVisibility,
    resetColumnVisibility
  };
}
