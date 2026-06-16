/**
 * 广告数据统计维度常量
 * @file constants/adDataDimension.js
 */

import { logger } from '../utils/logger';

/** @typedef {'country' | 'ad_unit' | 'ad_unit_country'} AdDataDimension */

/** 交叉维度：按广告单元+国家 */
export const AD_UNIT_COUNTRY_DIMENSION = 'ad_unit_country';

/** 已废弃别名，读取偏好时自动迁移 */
export const LEGACY_CROSS_DIMENSION = 'country_ad_unit';

export const AD_DATA_DIMENSION_OPTIONS = [
  { value: 'country', label: '按国家' },
  { value: 'ad_unit', label: '按广告单元' },
  { value: AD_UNIT_COUNTRY_DIMENSION, label: '按广告单元+国家' }
];

export const DEFAULT_AD_DATA_DIMENSION = 'country';

const AD_DATA_DIMENSION_STORAGE_PREFIX = 'adData_dimension';

const AD_DATA_DIMENSION_VALUES = new Set(
  AD_DATA_DIMENSION_OPTIONS.map((item) => item.value)
);

export const AD_DATA_DIMENSION_HINTS = {
  country: '仅展示国家维度数据（不含广告单元细分），避免与国家/单元 API 重复统计。',
  ad_unit: '仅展示广告单元维度数据（国家显示为全部区域），不含按国家拆分的数据。',
  [AD_UNIT_COUNTRY_DIMENSION]: '使用广告单元+国家交叉数据源，按日期+产品+广告单元汇总（所有国家合并）；可按广告单元、国家筛选。'
};

export function normalizeAdDataDimension(dimension) {
  if (dimension === LEGACY_CROSS_DIMENSION) {
    return AD_UNIT_COUNTRY_DIMENSION;
  }
  return dimension;
}

export function isValidAdDataDimension(dimension) {
  const normalized = normalizeAdDataDimension(dimension);
  return AD_DATA_DIMENSION_VALUES.has(normalized);
}

export function isAdUnitCountryDimension(dimension) {
  return normalizeAdDataDimension(dimension) === AD_UNIT_COUNTRY_DIMENSION;
}

function buildAdDataDimensionStorageKey(userId) {
  const id = userId != null && userId !== '' ? String(userId) : 'anonymous';
  return `${AD_DATA_DIMENSION_STORAGE_PREFIX}_${id}`;
}

/** 读取当前用户上次选择的统计维度（客户/管理员各自独立） */
export function loadAdDataDimensionPreference(userId) {
  try {
    const saved = localStorage.getItem(buildAdDataDimensionStorageKey(userId));
    if (saved && isValidAdDataDimension(saved)) {
      return normalizeAdDataDimension(saved);
    }
  } catch (error) {
    logger.error('加载统计维度偏好失败:', error);
  }
  return DEFAULT_AD_DATA_DIMENSION;
}

/** 持久化统计维度选择，下次登录默认使用 */
export function saveAdDataDimensionPreference(userId, dimension) {
  const normalized = normalizeAdDataDimension(dimension);
  if (!isValidAdDataDimension(normalized)) {
    return;
  }
  try {
    localStorage.setItem(buildAdDataDimensionStorageKey(userId), normalized);
  } catch (error) {
    logger.error('保存统计维度偏好失败:', error);
  }
}

export function showCountryFilterForDimension(dimension) {
  const dim = normalizeAdDataDimension(dimension);
  return dim === 'country' || dim === AD_UNIT_COUNTRY_DIMENSION;
}

export function showAdUnitFilterForDimension(dimension) {
  const dim = normalizeAdDataDimension(dimension);
  return dim === 'ad_unit' || dim === AD_UNIT_COUNTRY_DIMENSION;
}

/** 交叉维度下筛选区先展示广告单元、后展示国家 */
export function showAdUnitBeforeCountryInFilter(dimension) {
  return isAdUnitCountryDimension(dimension);
}
