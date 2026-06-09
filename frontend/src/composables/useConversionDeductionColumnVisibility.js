/**
 * 组合式函数 - 扣减配置列显隐
 * @file composables/useConversionDeductionColumnVisibility.js
 */
import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'conversionDeductionManagement_columnVisibility';

/**
 * 组合式函数 - 扣减配置列显隐
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useConversionDeductionColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      level: true,
      target_name: true,
      advertiser_name: true,
      volume_deduction: true,
      amount_deduction: true,
      priority: true,
      is_active: true,
    }),
    getSavableColumns: (v) => ({
      level: v.level,
      advertiser_name: v.advertiser_name,
      volume_deduction: v.volume_deduction,
      amount_deduction: v.amount_deduction,
      priority: v.priority,
      is_active: v.is_active,
    }),
    pinColumns: ['id', 'target_name'],
  });
}
