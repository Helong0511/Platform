/**
 * 组合式函数 - Offer 表格列显隐持久化
 * @file composables/useOfferColumnVisibility.js
 */
import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'offerManagement_columnVisibility';

/**
 * 组合式函数 - Offer 表格列显隐持久化
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useOfferColumnVisibility(isAdmin) {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      offer_name: true,
      advertiser_name: isAdmin.value,
      advertiser_offer_id: isAdmin.value,
      payout: isAdmin.value,
      affiliate_payout: true,
      country: true,
      category: true,
      type: true,
      upstream_cap: isAdmin.value,
      downstream_cap: true,
      preview_link: true,
      downstream_tracklink: true,
      click_validity_hours: isAdmin.value,
      assigned_publishers: isAdmin.value,
      status: true,
      is_active: isAdmin.value,
      created_at: true,
      updated_at: true,
    }),
    getSavableColumns: (v) => ({
      advertiser_name: v.advertiser_name,
      advertiser_offer_id: v.advertiser_offer_id,
      payout: v.payout,
      affiliate_payout: v.affiliate_payout,
      country: v.country,
      category: v.category,
      type: v.type,
      upstream_cap: v.upstream_cap,
      downstream_cap: v.downstream_cap,
      preview_link: v.preview_link,
      downstream_tracklink: v.downstream_tracklink,
      click_validity_hours: v.click_validity_hours,
      assigned_publishers: v.assigned_publishers,
      status: v.status,
      is_active: v.is_active,
      created_at: v.created_at,
      updated_at: v.updated_at,
    }),
    pinColumns: ['id', 'offer_name'],
  });
}
