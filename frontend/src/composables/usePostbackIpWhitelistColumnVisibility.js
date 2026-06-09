/**
 * 组合式函数 - Postback IP 白名单列显隐
 * @file composables/usePostbackIpWhitelistColumnVisibility.js
 */
import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'postbackIpWhitelist_columnVisibility';

/**
 * 组合式函数 - Postback IP 白名单列显隐
 * @returns {Object} 响应式状态与业务操作方法
 */
export function usePostbackIpWhitelistColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      ip_address: true,
      description: true,
      is_active: true,
      created_at: true,
      updated_at: true
    }),
    getSavableColumns: (v) => ({
      description: v.description,
      is_active: v.is_active,
      created_at: v.created_at,
      updated_at: v.updated_at
    }),
    pinColumns: ['id', 'ip_address']
  });
}
