import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'clientUserManagement_columnVisibility';

export function useClientUserManagementColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      name: true,
      created_at: true
    }),
    getSavableColumns: (v) => ({
      id: v.id,
      created_at: v.created_at
    }),
    pinColumns: ['name']
  });
}
