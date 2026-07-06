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

/** 明细维护：显示全部行级数据，不做统计维度互斥筛选 */
export const AD_DATA_DETAIL_ALL_DIMENSION = 'all';

export const AD_DATA_DIMENSION_OPTIONS = [
  { value: 'country', label: '按国家' },
  { value: 'ad_unit', label: '按广告单元' },
  { value: AD_UNIT_COUNTRY_DIMENSION, label: '按广告单元+国家' }
];

/** 明细维护页专用维度选项（含全部明细） */
export const AD_DATA_DETAIL_DIMENSION_OPTIONS = [
  { value: AD_DATA_DETAIL_ALL_DIMENSION, label: '全部明细' },
  ...AD_DATA_DIMENSION_OPTIONS
];

export const DEFAULT_AD_DATA_DIMENSION = 'country';

/** 明细维护页默认维度：显示全部行，避免 Zhisuo 纯 unit/country 在交叉维度下被滤掉 */
export const DEFAULT_AD_DATA_DETAIL_DIMENSION = AD_DATA_DETAIL_ALL_DIMENSION;

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
const AD_DATA_DETAIL_DIMENSION_STORAGE_PREFIX = 'adData_detail_dimension';

const AD_DATA_DIMENSION_VALUES = new Set(
  AD_DATA_DIMENSION_OPTIONS.map((item) => item.value)
);

const AD_DATA_DETAIL_DIMENSION_VALUES = new Set(
  AD_DATA_DETAIL_DIMENSION_OPTIONS.map((item) => item.value)
);

export const AD_DATA_DIMENSION_HINTS = {
  [AD_DATA_DETAIL_ALL_DIMENSION]:
    '显示全部行级明细（含智索 unit/country、GAM 交叉等），适合维护与核对。统计汇总请用每日统计子菜单。',
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

export function isValidAdDataDetailDimension(dimension) {
  const normalized = normalizeAdDataDetailDimension(dimension);
  return AD_DATA_DETAIL_DIMENSION_VALUES.has(normalized);
}

export function normalizeAdDataDetailDimension(dimension) {
  if (dimension === LEGACY_CROSS_DIMENSION) {
    return AD_UNIT_COUNTRY_DIMENSION;
  }
  if (dimension === AD_DATA_DETAIL_ALL_DIMENSION) {
    return AD_DATA_DETAIL_ALL_DIMENSION;
  }
  return normalizeAdDataDimension(dimension);
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

function buildAdDataDetailDimensionStorageKey(userId) {
  const id = userId != null && userId !== '' ? String(userId) : 'anonymous';
  return `${AD_DATA_DETAIL_DIMENSION_STORAGE_PREFIX}_${id}`;
}

/** 明细维护页：读取上次选择的统计维度（与每日统计页偏好独立） */
export function loadAdDataDetailDimensionPreference(userId) {
  try {
    const saved = localStorage.getItem(buildAdDataDetailDimensionStorageKey(userId));
    if (saved && isValidAdDataDetailDimension(saved)) {
      return normalizeAdDataDetailDimension(saved);
    }
  } catch (error) {
    logger.error('加载明细维护统计维度偏好失败:', error);
  }
  return DEFAULT_AD_DATA_DETAIL_DIMENSION;
}

/** 明细维护页：持久化统计维度选择 */
export function saveAdDataDetailDimensionPreference(userId, dimension) {
  const normalized = normalizeAdDataDetailDimension(dimension);
  if (!isValidAdDataDetailDimension(normalized)) {
    return;
  }
  try {
    localStorage.setItem(buildAdDataDetailDimensionStorageKey(userId), normalized);
  } catch (error) {
    logger.error('保存明细维护统计维度偏好失败:', error);
  }
}

export function showCountryFilterForDimension(dimension) {
  const dim = normalizeAdDataDetailDimension(dimension);
  if (dim === AD_DATA_DETAIL_ALL_DIMENSION) {
    return true;
  }
  return dim === 'country' || dim === AD_UNIT_COUNTRY_DIMENSION;
}

export function showAdUnitFilterForDimension(dimension) {
  const dim = normalizeAdDataDetailDimension(dimension);
  if (dim === AD_DATA_DETAIL_ALL_DIMENSION) {
    return true;
  }
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

  const appendValue = (key, value) => {
    if (value == null || value === '') {
      return;
    }
    if (Array.isArray(value)) {
      const normalized = value.map((item) => String(item)).filter(Boolean);
      if (normalized.length > 0) {
        params[key] = normalized.join(',');
      }
      return;
    }
    params[key] = value;
  };

  if (allowCountry) {
    appendValue('country_code', countryCode);
  }
  if (allowAdUnit) {
    appendValue('ad_unit', adUnit);
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
  const dim = normalizeAdDataDetailDimension(dimension || DEFAULT_AD_DATA_DIMENSION);
  const result = { ...columnVisibility };
  if (dim === AD_DATA_DETAIL_ALL_DIMENSION) {
    result.ad_unit = true;
    result.country_name_zh = true;
    return result;
  }
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

/** ad_data 数据来源中文标签（与 app/core/ad_data_metadata.py 一致） */
export const AD_DATA_SOURCE_LABELS = {
  zhisuo: '智索',
  gam: 'GAM',
  pomiad: 'Pomiad',
  addermobi: 'Addermobi',
  skymobi: 'Skymobi',
  huguang: 'Huguang',
  tqt: 'TQT',
  tbsj: '通百世家(yangyangdeyi)',
  excel: 'Excel 导入',
  legacy: '历史',
  unknown: '未知'
};

/** 上游 API 拉数来源（编辑下拉优先顺序） */
export const UPSTREAM_API_DATA_SOURCES = [
  'zhisuo',
  'gam',
  'pomiad',
  'addermobi',
  'skymobi',
  'huguang',
  'tqt',
  'tbsj'
];

/** 明细维护编辑：其它来源（手工/历史） */
export const AD_DATA_SOURCE_MANUAL_OPTIONS = ['excel', 'legacy', 'unknown'];

/** ad_data 报表维度中文标签（与 app/core/ad_data_metadata.py 一致） */
export const AD_DATA_REPORT_TYPE_LABELS = {
  unit: '广告单元',
  country: '国家',
  cross: '交叉',
  daily: '日报',
  legacy: '历史'
};

/** 统计维度报表类型（编辑下拉优先） */
export const AD_DATA_REPORT_TYPE_DETAIL_OPTIONS = ['unit', 'country', 'cross', 'daily'];

/** 其它报表类型 */
export const AD_DATA_REPORT_TYPE_OTHER_OPTIONS = ['legacy'];

/** 各类型说明（与后端 REPORT_TYPE_HINTS 一致） */
export const AD_DATA_REPORT_TYPE_HINTS = {
  unit: '按广告单元，无国家；智索 unit、GAM ad_unit',
  country: '按国家，无广告单元；智索 country、TQT、Huguang',
  cross: '国家+广告单元；Addermobi、Skymobi、Pomiad、GAM country',
  daily: '日汇总，无国家无单元；智索 daily 兜底、GAM daily',
  legacy: '历史或未标注；新入库会自动按行形态推断'
};

export function formatAdDataSourceLabel(value) {
  const key = String(value || 'legacy').trim().toLowerCase() || 'legacy';
  return AD_DATA_SOURCE_LABELS[key] || key;
}

export function formatAdDataReportTypeLabel(value) {
  const key = String(value || 'legacy').trim().toLowerCase() || 'legacy';
  return AD_DATA_REPORT_TYPE_LABELS[key] || key;
}

/** 明细维护编辑：数据来源选项（上游 API + 手工/历史） */
export function buildAdDataSourceOptions(currentValue) {
  const keys = new Set([
    ...UPSTREAM_API_DATA_SOURCES,
    ...AD_DATA_SOURCE_MANUAL_OPTIONS
  ]);
  const raw = String(currentValue || '').trim().toLowerCase();
  if (raw) keys.add(raw);
  const ordered = [
    ...UPSTREAM_API_DATA_SOURCES,
    ...AD_DATA_SOURCE_MANUAL_OPTIONS.filter((k) => keys.has(k)),
    ...[...keys].filter(
      (k) => !UPSTREAM_API_DATA_SOURCES.includes(k) && !AD_DATA_SOURCE_MANUAL_OPTIONS.includes(k)
    )
  ];
  return [...new Set(ordered)].map((value) => ({
    value,
    label: `${formatAdDataSourceLabel(value)} (${value})`
  }));
}

/** @deprecated 使用 buildAdDataSourceOptions */
export const AD_DATA_SOURCE_OPTIONS = buildAdDataSourceOptions();

/** 明细维护编辑：报表类型选项（统计维度 + 历史） */
export function buildAdDataReportTypeOptions(currentValue) {
  const keys = new Set([
    ...AD_DATA_REPORT_TYPE_DETAIL_OPTIONS,
    ...AD_DATA_REPORT_TYPE_OTHER_OPTIONS
  ]);
  const raw = String(currentValue || '').trim().toLowerCase();
  if (raw) keys.add(raw);
  const ordered = [
    ...AD_DATA_REPORT_TYPE_DETAIL_OPTIONS,
    ...AD_DATA_REPORT_TYPE_OTHER_OPTIONS.filter((k) => keys.has(k)),
    ...[...keys].filter(
      (k) =>
        !AD_DATA_REPORT_TYPE_DETAIL_OPTIONS.includes(k) &&
        !AD_DATA_REPORT_TYPE_OTHER_OPTIONS.includes(k)
    )
  ];
  return [...new Set(ordered)].map((value) => ({
    value,
    label: `${formatAdDataReportTypeLabel(value)} (${value})`,
    hint: AD_DATA_REPORT_TYPE_HINTS[value] || ''
  }));
}

/** @deprecated 使用 buildAdDataReportTypeOptions */
export const AD_DATA_REPORT_TYPE_OPTIONS = buildAdDataReportTypeOptions();
