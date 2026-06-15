/**
 * 广告数据统计维度常量
 * @file constants/adDataDimension.js
 */

import { logger } from '../utils/logger';

/** @typedef {'country' | 'ad_unit' | 'country_ad_unit'} AdDataDimension */

export const AD_DATA_DIMENSION_OPTIONS = [
  { value: 'country', label: '按国家' },
  { value: 'ad_unit', label: '按广告单元' },
  { value: 'country_ad_unit', label: '按国家+广告单元' }
];

export const DEFAULT_AD_DATA_DIMENSION = 'country';

const AD_DATA_DIMENSION_STORAGE_PREFIX = 'adData_dimension';

const AD_DATA_DIMENSION_VALUES = new Set(
  AD_DATA_DIMENSION_OPTIONS.map((item) => item.value)
);

export const AD_DATA_DIMENSION_HINTS = {
  country: '仅展示国家维度数据（不含广告单元细分），避免与国家/单元 API 重复统计。',
  ad_unit: '仅展示广告单元维度数据（国家显示为全部区域），不含按国家拆分的数据。',
  country_ad_unit: '展示国家与广告单元交叉明细数据。'
};

export function isValidAdDataDimension(dimension) {
  return AD_DATA_DIMENSION_VALUES.has(dimension);
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
      return saved;
    }
  } catch (error) {
    logger.error('加载统计维度偏好失败:', error);
  }
  return DEFAULT_AD_DATA_DIMENSION;
}

/** 持久化统计维度选择，下次登录默认使用 */
export function saveAdDataDimensionPreference(userId, dimension) {
  if (!isValidAdDataDimension(dimension)) {
    return;
  }
  try {
    localStorage.setItem(buildAdDataDimensionStorageKey(userId), dimension);
  } catch (error) {
    logger.error('保存统计维度偏好失败:', error);
  }
}

export function showCountryFilterForDimension(dimension) {
  return dimension === 'country' || dimension === 'country_ad_unit';
}

export function showAdUnitFilterForDimension(dimension) {
  return dimension === 'ad_unit' || dimension === 'country_ad_unit';
}
