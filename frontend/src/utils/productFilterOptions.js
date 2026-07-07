/**
 * 广告数据等产品筛选项：归属类型标注与展示文案
 * @file utils/productFilterOptions.js
 */

/** @typedef {'current'|'historical'|'both'} ProductOwnershipType */

export const PRODUCT_OWNERSHIP_HINT =
  '产品列表随日期范围变化：「当前」为名下产品；「历史」为所选日期内曾归属但已转移的产品；「当前+历史」表示两种口径均匹配。';

/**
 * @param {string} name
 * @param {ProductOwnershipType|null|undefined} ownershipType
 * @returns {string}
 */
export function formatProductFilterLabel(name, ownershipType) {
  const base = name || '未知产品';
  if (!ownershipType) {
    return base;
  }
  const suffixMap = {
    current: ' [当前]',
    historical: ' [历史]',
    both: ' [当前+历史]',
  };
  return `${base}${suffixMap[ownershipType] || ''}`;
}

/**
 * @param {ProductOwnershipType|null|undefined} ownershipType
 * @returns {{ text: string, type: 'success'|'info'|'warning' }|null}
 */
export function getProductOwnershipTag(ownershipType) {
  switch (ownershipType) {
    case 'current':
      return { text: '当前', type: 'success' };
    case 'historical':
      return { text: '历史', type: 'info' };
    case 'both':
      return { text: '当前+历史', type: 'warning' };
    default:
      return null;
  }
}

/**
 * 将 API 产品项转为下拉 option
 * @param {Object} item
 * @returns {{ id: number, value: string, name: string, label: string, ownershipType: ProductOwnershipType|null }}
 */
export function mapApiProductToFilterOption(item) {
  const name = item?.name || '未知产品';
  const ownershipType = item?.ownership_type || null;
  return {
    id: item.id,
    value: String(item.id),
    name,
    ownershipType,
    label: formatProductFilterLabel(name, ownershipType),
  };
}

/**
 * 选项列表中是否包含归属标注（用于决定是否展示说明）
 * @param {Array<{ ownershipType?: ProductOwnershipType|null }>} options
 */
export function hasProductOwnershipLabels(options = []) {
  return options.some((item) => item?.ownershipType);
}
