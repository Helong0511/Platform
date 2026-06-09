/**
 * 广告数据表格列显隐管理
 * @file composables/useAdDataColumnVisibility.js
 *
 * 封装广告数据、每日汇总、TB 搜索等页面的列显隐与 localStorage 持久化。
 */
import { useTableColumnVisibility } from './useTableColumnVisibility';

/**
 * @param {string} storageKey
 * @param {() => Record<string, boolean>} getDefaultColumns
 * @param {string[]} savableKeys 持久化时保存的列键
 */
/**
 * 组合式函数 - 广告数据列显隐
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useAdDataColumnVisibility(storageKey, getDefaultColumns, savableKeys) {
  return useTableColumnVisibility(storageKey, {
    getDefaultColumns,
    getSavableColumns: (v) => {
      const toSave = {};
      savableKeys.forEach((key) => {
        toSave[key] = v[key];
      });
      return toSave;
    },
    pinColumns: ['date', 'product_name']
  });
}

/** 广告明细 / 日报默认列配置 */
export function createAdDataDefaultColumns(getIsAdmin) {
  const admin = typeof getIsAdmin === 'function' ? getIsAdmin() : getIsAdmin;
  return {
    date: true,
    user_name: admin,
    product_name: true,
    ad_unit: true,
    country_name_zh: true,
    request_count: true,
    match_count: true,
    coverage_rate: true,
    display_count: true,
    display_rate: true,
    click_count: true,
    click_rate: true,
    viewability_rate: true,
    cpc: true,
    pageviews: true,
    ecpm_after_deduct: true,
    ecpm_before_deduct: admin,
    revenue_after_deduct: true,
    revenue_before_deduct: admin
  };
}

export const AD_DATA_SAVABLE_COLUMN_KEYS = [
  'user_name',
  'ad_unit',
  'country_name_zh',
  'request_count',
  'match_count',
  'coverage_rate',
  'display_count',
  'display_rate',
  'click_count',
  'click_rate',
  'viewability_rate',
  'cpc',
  'pageviews',
  'ecpm_after_deduct',
  'ecpm_before_deduct',
  'revenue_after_deduct',
  'revenue_before_deduct'
];
