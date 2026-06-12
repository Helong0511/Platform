/**
 * 组合式函数 - 用户表格列显隐
 * @file composables/useUserColumnVisibility.js
 */
import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'userManagement_columnVisibility';

/**
 * 组合式函数 - 用户表格列显隐
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useUserColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      username: true,
      full_name: true,
      role: true,
      email: true,
      company_name: true,
      contact_person: true,
      is_active: true,
      api_enabled: true,
      password_change_enabled: true,
      created_at: true,
    }),
    getSavableColumns: (v) => ({
      full_name: v.full_name,
      role: v.role,
      email: v.email,
      company_name: v.company_name,
      contact_person: v.contact_person,
      is_active: v.is_active,
      api_enabled: v.api_enabled,
      password_change_enabled: v.password_change_enabled,
      created_at: v.created_at,
    }),
    pinColumns: ['id', 'username'],
  });
}
