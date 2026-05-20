import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'discountManagement_columnVisibility';

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
