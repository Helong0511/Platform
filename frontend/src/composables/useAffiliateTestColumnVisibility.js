import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'affiliateTest_columnVisibility';

export function useAffiliateTestColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      publisher_name: true,
      offer_name: true,
      click_id: true,
      price: true,
      country: true,
      status: true,
      postback_time: true
    }),
    getSavableColumns: (v) => ({
      publisher_name: v.publisher_name,
      price: v.price,
      country: v.country,
      status: v.status,
      postback_time: v.postback_time
    }),
    pinColumns: ['offer_name', 'click_id']
  });
}
