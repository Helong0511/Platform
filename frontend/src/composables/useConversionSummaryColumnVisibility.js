/**
 * 组合式函数 - 转化总览列显隐
 * @file composables/useConversionSummaryColumnVisibility.js
 */
import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'conversionSummary_columnVisibility';

/**
 * 转化总览表格列显示偏好（localStorage）。
 * @param {import('vue').ComputedRef<boolean>} isAdmin
 */
/**
 * 组合式函数 - 转化总览列显隐
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useConversionSummaryColumnVisibility(isAdmin) {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      offer_id: true,
      offer_name: true,
      advertiser_name: isAdmin.value,
      publisher_name: true,
      click_count: true,
      conversion_count: true,
      cr: true,
      po: isAdmin.value,
      po_after_discount: true,
      profit: isAdmin.value,
      adv_po: isAdmin.value,
      pub_po: true,
      geo: true,
    }),
    getSavableColumns: (v) => ({
      advertiser_name: v.advertiser_name,
      publisher_name: v.publisher_name,
      click_count: v.click_count,
      conversion_count: v.conversion_count,
      cr: v.cr,
      po: v.po,
      po_after_discount: v.po_after_discount,
      profit: v.profit,
      adv_po: v.adv_po,
      pub_po: v.pub_po,
      geo: v.geo,
    }),
    pinColumns: ['offer_id', 'offer_name'],
  });
}
