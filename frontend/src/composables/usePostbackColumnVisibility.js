import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'postbackManagement_columnVisibility';

/**
 * Postback 转化列表列显示偏好（localStorage）。
 * @param {import('vue').ComputedRef<boolean>} isAdmin
 */
export function usePostbackColumnVisibility(isAdmin) {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      platform: true,
      conversion_id: true,
      click_offer_name: true,
      click_publisher_name: true,
      click_advertiser_name: true,
      click_time: true,
      conversion_status: true,
      event_name: true,
      event_value: true,
      original_payout: isAdmin.value,
      payout: true,
      devad_id: true,
      os: true,
      carrier: true,
      gid: true,
      product_id: true,
      client_id: true,
      created_at: true,
      has_notification: true,
    }),
    getSavableColumns: (v) => ({
      platform: v.platform,
      click_offer_name: v.click_offer_name,
      click_publisher_name: v.click_publisher_name,
      click_advertiser_name: v.click_advertiser_name,
      click_time: v.click_time,
      conversion_status: v.conversion_status,
      event_name: v.event_name,
      event_value: v.event_value,
      original_payout: v.original_payout,
      payout: v.payout,
      devad_id: v.devad_id,
      os: v.os,
      carrier: v.carrier,
      gid: v.gid,
      product_id: v.product_id,
      client_id: v.client_id,
      created_at: v.created_at,
      has_notification: v.has_notification,
    }),
    pinColumns: ['id', 'conversion_id'],
  });
}
