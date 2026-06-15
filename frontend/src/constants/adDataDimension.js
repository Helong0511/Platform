/**
 * 广告数据统计维度常量
 * @file constants/adDataDimension.js
 */

/** @typedef {'country' | 'ad_unit' | 'country_ad_unit'} AdDataDimension */

export const AD_DATA_DIMENSION_OPTIONS = [
  { value: 'country', label: '按国家' },
  { value: 'ad_unit', label: '按广告单元' },
  { value: 'country_ad_unit', label: '按国家+广告单元' }
];

export const DEFAULT_AD_DATA_DIMENSION = 'country';

export const AD_DATA_DIMENSION_HINTS = {
  country: '仅展示国家维度数据（不含广告单元细分），避免与国家/单元 API 重复统计。',
  ad_unit: '仅展示广告单元维度数据（国家显示为全部区域），不含按国家拆分的数据。',
  country_ad_unit: '展示国家与广告单元交叉明细数据。'
};

export function showCountryFilterForDimension(dimension) {
  return dimension === 'country' || dimension === 'country_ad_unit';
}

export function showAdUnitFilterForDimension(dimension) {
  return dimension === 'ad_unit' || dimension === 'country_ad_unit';
}
