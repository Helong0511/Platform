import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'sessionManagement_columnVisibility';

export function useSessionManagementColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      ip_address: true,
      device_info: true,
      user_agent: true,
      location: true,
      is_active: true,
      created_at: true,
      last_activity: true,
      expires_at: true
    }),
    getSavableColumns: (v) => ({
      ip_address: v.ip_address,
      device_info: v.device_info,
      user_agent: v.user_agent,
      location: v.location,
      is_active: v.is_active,
      last_activity: v.last_activity,
      expires_at: v.expires_at
    }),
    pinColumns: ['id', 'created_at']
  });
}
