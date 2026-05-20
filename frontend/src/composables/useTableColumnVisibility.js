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
export function useTableColumnVisibility(storageKey, options) {
  const { getDefaultColumns, getSavableColumns, pinColumns = [] } = options;
  const columnSettingVisible = ref(false);
  const columnVisibility = reactive(getDefaultColumns());

  const columnVisibilityArray = computed({
    get: () => Object.keys(columnVisibility).filter((key) => columnVisibility[key]),
    set: (value) => {
      Object.keys(columnVisibility).forEach((key) => {
        columnVisibility[key] = value.includes(key);
      });
    },
  });

  const loadColumnVisibility = () => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        Object.assign(columnVisibility, getDefaultColumns(), JSON.parse(saved));
        pinColumns.forEach((key) => {
          if (key in columnVisibility) {
            columnVisibility[key] = true;
          }
        });
      }
    } catch (error) {
      logger.error('加载列显示设置失败:', error);
    }
  };

  const saveColumnVisibility = () => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(getSavableColumns(columnVisibility)));
      columnSettingVisible.value = false;
      ElMessage.success('列显示设置已保存');
    } catch (error) {
      logger.error('保存列显示设置失败:', error);
      ElMessage.error('保存设置失败');
    }
  };

  return {
    columnSettingVisible,
    columnVisibility,
    columnVisibilityArray,
    loadColumnVisibility,
    saveColumnVisibility,
  };
}
