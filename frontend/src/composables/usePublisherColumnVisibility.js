/**
 * 组合式函数 - 渠道表格列显隐
 * @file composables/usePublisherColumnVisibility.js
 */
import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'publisherManagement_columnVisibility';

/**
 * 组合式函数 - 渠道表格列显隐
 * @returns {Object} 响应式状态与业务操作方法
 */
export function usePublisherColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      publisher_name: true,
      client_name: true,
      email: true,
      price_discount: true,
      postback_url: true,
      postback_method: true,
      active_advertiser_count: true,
      is_active: true,
      created_at: true,
    }),
    getSavableColumns: (v) => ({
      client_name: v.client_name,
      email: v.email,
      price_discount: v.price_discount,
      postback_url: v.postback_url,
      postback_method: v.postback_method,
      active_advertiser_count: v.active_advertiser_count,
      is_active: v.is_active,
      created_at: v.created_at,
    }),
    pinColumns: ['id', 'publisher_name'],
  });
}
