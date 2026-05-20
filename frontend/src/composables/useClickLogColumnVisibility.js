import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'clickLog_columnVisibility';

export function useClickLogColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      click_id: true,
      click_time: true,
      offer_name: true,
      publisher_name: true,
      advertiser_name: true,
      short_code: true,
      ip: true,
      country: true,
      device_type: true,
      os: true,
      browser: true,
      device_brand: true,
      is_bot: true,
      referer: true,
      conversion_id: true,
    }),
    getSavableColumns: (v) => ({
      offer_name: v.offer_name,
      publisher_name: v.publisher_name,
      advertiser_name: v.advertiser_name,
      short_code: v.short_code,
      ip: v.ip,
      country: v.country,
      device_type: v.device_type,
      os: v.os,
      browser: v.browser,
      device_brand: v.device_brand,
      is_bot: v.is_bot,
      referer: v.referer,
      conversion_id: v.conversion_id,
    }),
    pinColumns: ['click_id', 'click_time'],
  });
}
