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

/** 每日统计子菜单页配置（固定维度，不再使用下拉选择） */
export const DAILY_REPORT_PAGE_KEYS = {
  SUMMARY: 'summary',
  COUNTRY: 'country',
  AD_UNIT: 'ad_unit',
  CROSS: 'cross'
};

/** @type {Record<string, { key: string, label: string, path: string, dimension: string, title: string, hint: string, showCountryFilter: boolean, showAdUnitFilter: boolean, splitByCountry: boolean, showCountryColumn: boolean }>} */
export const DAILY_REPORT_PAGE_CONFIG = {
  [DAILY_REPORT_PAGE_KEYS.SUMMARY]: {
    key: DAILY_REPORT_PAGE_KEYS.SUMMARY,
    label: '每日统计',
    path: '/app/ad-data/daily-report',
    dimension: 'country',
    title: '每日统计数据',
    hint: '按日期+产品汇总，不区分国家与广告单元。',
    showCountryFilter: false,
    showAdUnitFilter: false,
    splitByCountry: false,
    showCountryColumn: false
  },
  [DAILY_REPORT_PAGE_KEYS.COUNTRY]: {
    key: DAILY_REPORT_PAGE_KEYS.COUNTRY,
    label: '国家数据',
    path: '/app/ad-data/daily-report/country',
    dimension: 'country',
    title: '国家数据',
    hint: '按日期+产品+国家汇总，可按国家筛选。',
    showCountryFilter: true,
    showAdUnitFilter: false,
    splitByCountry: true,
    showCountryColumn: true
  },
  [DAILY_REPORT_PAGE_KEYS.AD_UNIT]: {
    key: DAILY_REPORT_PAGE_KEYS.AD_UNIT,
    label: '广告单元',
    path: '/app/ad-data/daily-report/ad-unit',
    dimension: 'ad_unit',
    title: '广告单元数据',
    hint: '按日期+产品+广告单元汇总；Zhisuo 双 API 仅计入单元报告。',
    showCountryFilter: false,
    showAdUnitFilter: true,
    splitByCountry: false,
    showCountryColumn: false
  },
  [DAILY_REPORT_PAGE_KEYS.CROSS]: {
    key: DAILY_REPORT_PAGE_KEYS.CROSS,
    label: '详细报表',
    path: '/app/ad-data/detail-report',
    dimension: AD_UNIT_COUNTRY_DIMENSION,
    title: '详细报表',
    hint: '交叉明细日汇总（日期+产品+广告单元+国家），可按广告单元、国家筛选。',
    showCountryFilter: true,
    showAdUnitFilter: true,
    splitByCountry: false,
    showCountryColumn: true
  }
};

/** 侧栏展示顺序 */
export const DAILY_REPORT_MENU_ITEMS = [
  DAILY_REPORT_PAGE_CONFIG[DAILY_REPORT_PAGE_KEYS.SUMMARY],
  DAILY_REPORT_PAGE_CONFIG[DAILY_REPORT_PAGE_KEYS.COUNTRY],
  DAILY_REPORT_PAGE_CONFIG[DAILY_REPORT_PAGE_KEYS.AD_UNIT],
  DAILY_REPORT_PAGE_CONFIG[DAILY_REPORT_PAGE_KEYS.CROSS]
];

/**
 * @param {string} [pageKey]
 */
export function getDailyReportPageConfig(pageKey) {
  return (
    DAILY_REPORT_PAGE_CONFIG[pageKey] ||
    DAILY_REPORT_PAGE_CONFIG[DAILY_REPORT_PAGE_KEYS.SUMMARY]
  );
}

const AD_DATA_DIMENSION_STORAGE_PREFIX = 'adData_dimension';

const AD_DATA_DIMENSION_VALUES = new Set(
  AD_DATA_DIMENSION_OPTIONS.map((item) => item.value)
);

export const AD_DATA_DIMENSION_HINTS = {
  country:
    '按日期+产品汇总（合并所有国家）。Zhisuo 双 API 客户仅计入国家报告；Addermobi 等仅交叉数据时自动使用交叉行。',
  ad_unit:
    '按日期+产品+广告单元汇总。Zhisuo 双 API 客户仅计入广告单元报告；无单元明细时使用交叉行。',
  [AD_UNIT_COUNTRY_DIMENSION]:
    '仅交叉明细（同时含国家与广告单元，如 Addermobi）。Zhisuo 双 API 纯国家/纯单元数据不在此维度展示。'
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

/**
 * 构建列表/导出请求参数时，仅附带当前维度（及页面显隐）允许的筛选项。
 * @param {Object} [options.enableCountryFilter] 页面显式关闭国家筛选时传 false（如每日统计汇总页）
 * @param {Object} [options.enableAdUnitFilter] 页面显式关闭广告单元筛选时传 false
 */
export function appendDimensionAwareFilters(
  params,
  { dimension, countryCode, adUnit, enableCountryFilter = null, enableAdUnitFilter = null }
) {
  const dim = normalizeAdDataDimension(dimension || DEFAULT_AD_DATA_DIMENSION);
  const allowCountry =
    enableCountryFilter === false
      ? false
      : enableCountryFilter === true || showCountryFilterForDimension(dim);
  const allowAdUnit =
    enableAdUnitFilter === false
      ? false
      : enableAdUnitFilter === true || showAdUnitFilterForDimension(dim);
  if (allowCountry && countryCode) {
    params.country_code = countryCode;
  }
  if (allowAdUnit && adUnit) {
    params.ad_unit = adUnit;
  }
  return params;
}

/**
 * 按统计维度调整表格列显隐（列设置仅控制展示，不影响查询）。
 * @param {Record<string, boolean>} columnVisibility
 * @param {string} [dimension]
 * @param {{ dailySummary?: boolean }} [options] dailySummary 为 true 时按日汇总展示规则隐藏无意义列
 */
export function applyDimensionColumnDefaults(columnVisibility, dimension, options = {}) {
  const { dailySummary = false, showCountryColumn = null } = options;
  const dim = normalizeAdDataDimension(dimension || DEFAULT_AD_DATA_DIMENSION);
  const result = { ...columnVisibility };
  if (dim === 'ad_unit' || isAdUnitCountryDimension(dim)) {
    result.ad_unit = true;
  }
  if (dim === 'country') {
    result.ad_unit = false;
  }
  if (showCountryColumn === true) {
    result.country_name_zh = true;
  } else if (showCountryColumn === false || dailySummary) {
    result.country_name_zh = false;
  }
  return result;
}
