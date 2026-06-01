import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'advertiserManagement_columnVisibility';

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
