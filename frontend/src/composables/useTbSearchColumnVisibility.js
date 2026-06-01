import {
  useAdDataColumnVisibility
} from './useAdDataColumnVisibility';

export function createTbSearchDefaultColumns(getIsAdmin) {
  const admin = typeof getIsAdmin === 'function' ? getIsAdmin() : getIsAdmin;
  return {
    date: true,
    user_name: admin,
    product_name: true,
    country_name_zh: true,
    redirects: true,
    searches: true,
    monetized: true,
    clicks: true,
    revenue: true,
    revenue_before_deduct: admin,
    rpm: true,
    rpm_before_deduct: admin
  };
}

export const TB_SEARCH_SAVABLE_COLUMN_KEYS = [
  'user_name',
  'country_name_zh',
  'redirects',
  'searches',
  'monetized',
  'clicks',
  'revenue',
  'revenue_before_deduct',
  'rpm',
  'rpm_before_deduct'
];

export function useTbSearchColumnVisibility(getIsAdmin) {
  return useAdDataColumnVisibility(
    'tbSearchData_columnVisibility',
    () => createTbSearchDefaultColumns(getIsAdmin),
    TB_SEARCH_SAVABLE_COLUMN_KEYS
  );
}
