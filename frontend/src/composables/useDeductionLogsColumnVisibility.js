import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'deductionLogs_columnVisibility';

export function useDeductionLogsColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      conversion_id: true,
      click_id: true,
      advertiser_name: true,
      offer_name: true,
      publisher_name: true,
      volume_deduction: true,
      amount_deduction: true,
      deduction_strategy: true,
      created_at: true
    }),
    getSavableColumns: (v) => ({
      conversion_id: v.conversion_id,
      advertiser_name: v.advertiser_name,
      offer_name: v.offer_name,
      publisher_name: v.publisher_name,
      volume_deduction: v.volume_deduction,
      amount_deduction: v.amount_deduction,
      deduction_strategy: v.deduction_strategy,
      created_at: v.created_at
    }),
    pinColumns: ['id', 'click_id']
  });
}
