/**
 * 组合式函数 - Cap 表格列显隐
 * @file composables/useCapColumnVisibility.js
 */
import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'capManagement_columnVisibility';

/**
 * 组合式函数 - Cap 表格列显隐
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useCapColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      cap_type: true,
      offer_name: true,
      advertiser_name: true,
      publisher_name: true,
      daily_cap: true,
      current_daily_count: true,
      total_cap: true,
      current_total_count: true,
      is_active: true,
    }),
    getSavableColumns: (v) => ({
      cap_type: v.cap_type,
      advertiser_name: v.advertiser_name,
      publisher_name: v.publisher_name,
      daily_cap: v.daily_cap,
      current_daily_count: v.current_daily_count,
      total_cap: v.total_cap,
      current_total_count: v.current_total_count,
      is_active: v.is_active,
    }),
    pinColumns: ['offer_name'],
  });
}
