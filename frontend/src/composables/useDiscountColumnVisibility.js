/**
 * 组合式函数 - 扣量列显隐
 * @file composables/useDiscountColumnVisibility.js
 */
import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'discountManagement_columnVisibility';

/**
 * 组合式函数 - 扣量列显隐
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useDiscountColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      discount_type: true,
      offer_name: true,
      publisher_name: true,
      discount_ratio: true,
      is_active: true,
      created_at: true,
    }),
    getSavableColumns: (v) => ({
      discount_type: v.discount_type,
      offer_name: v.offer_name,
      publisher_name: v.publisher_name,
      discount_ratio: v.discount_ratio,
      is_active: v.is_active,
      created_at: v.created_at,
    }),
  });
}
