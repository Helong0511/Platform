import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'userManagement_columnVisibility';

export function useUserColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      username: true,
      full_name: true,
      role: true,
      email: true,
      is_active: true,
      api_enabled: true,
      password_change_enabled: true,
      created_at: true,
    }),
    getSavableColumns: (v) => ({
      full_name: v.full_name,
      role: v.role,
      email: v.email,
      is_active: v.is_active,
      api_enabled: v.api_enabled,
      password_change_enabled: v.password_change_enabled,
      created_at: v.created_at,
    }),
    pinColumns: ['id', 'username'],
  });
}
