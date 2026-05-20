import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'auditLogManagement_columnVisibility';

export function useAuditLogColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      username: true,
      action_type: true,
      resource_type: true,
      resource_name: true,
      ip_address: true,
      request_method: true,
      request_path: true,
      status_code: true,
      success: true,
      created_at: true,
    }),
    getSavableColumns: (v) => ({
      username: v.username,
      action_type: v.action_type,
      resource_type: v.resource_type,
      resource_name: v.resource_name,
      ip_address: v.ip_address,
      request_method: v.request_method,
      request_path: v.request_path,
      status_code: v.status_code,
      success: v.success,
    }),
    pinColumns: ['id', 'created_at'],
  });
}
