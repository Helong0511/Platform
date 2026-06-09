/**
 * 组合式函数 - 客户用户管理列显隐
 * @file composables/useClientUserManagementColumnVisibility.js
 */
import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'clientUserManagement_columnVisibility';

/**
 * 组合式函数 - 客户用户管理列显隐
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useClientUserManagementColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      name: true,
      created_at: true
    }),
    getSavableColumns: (v) => ({
      id: v.id,
      created_at: v.created_at
    }),
    pinColumns: ['name']
  });
}
