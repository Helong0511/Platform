/**
 * 组合式函数 - 广告主管理列显隐
 * @file composables/useAdvertiserManagementColumnVisibility.js
 */
import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'advertiserManagement_columnVisibility';

/**
 * 组合式函数 - 广告主管理列显隐
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useAdvertiserManagementColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      advertiser_name: true,
      advertiser_params: true,
      mobile: true,
      email: true,
      is_active: true,
      created_at: true
    }),
    getSavableColumns: (v) => ({
      advertiser_params: v.advertiser_params,
      mobile: v.mobile,
      email: v.email,
      is_active: v.is_active,
      created_at: v.created_at
    }),
    pinColumns: ['id', 'advertiser_name']
  });
}
