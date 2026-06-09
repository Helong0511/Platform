/**
 * 组合式函数 - 第三方报表列显隐
 * @file composables/useThirdPartyReportColumnVisibility.js
 */
import { useTableColumnVisibility } from './useTableColumnVisibility';

const STORAGE_KEY = 'thirdPartyReportManagement_columnVisibility';

/**
 * 组合式函数 - 第三方报表列显隐
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useThirdPartyReportColumnVisibility() {
  return useTableColumnVisibility(STORAGE_KEY, {
    getDefaultColumns: () => ({
      id: true,
      source: true,
      adsid: true,
      event: true,
      conversion_id: true,
      currency: true,
      amount: true,
      status: true,
      attempt_count: true,
      response_status: true,
      log_id: true,
      use_hash: true,
      created_at: true,
      report_success_time: true,
      report_params: false,
    }),
    getSavableColumns: (v) => ({
      source: v.source,
      adsid: v.adsid,
      event: v.event,
      conversion_id: v.conversion_id,
      currency: v.currency,
      amount: v.amount,
      status: v.status,
      attempt_count: v.attempt_count,
      response_status: v.response_status,
      log_id: v.log_id,
      use_hash: v.use_hash,
      report_params: v.report_params,
      report_success_time: v.report_success_time,
    }),
    pinColumns: ['id', 'created_at'],
  });
}
