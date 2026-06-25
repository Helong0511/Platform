/**
 * 广告数据等多选筛选字段工具
 * @file utils/multiFilterValues.js
 */

/** 筛选值为空（未选 / 全部） */
export function isEmptyMultiFilter(value) {
  if (value == null || value === '') {
    return true;
  }
  if (Array.isArray(value)) {
    return value.length === 0;
  }
  return false;
}

/** 规范为字符串数组（兼容历史单选字符串） */
export function normalizeMultiFilterArray(value) {
  if (isEmptyMultiFilter(value)) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).filter(Boolean);
  }
  return [String(value)];
}

/** 将多选值写入请求参数（逗号分隔，空则跳过） */
export function appendCsvFilter(params, key, value) {
  const values = normalizeMultiFilterArray(value);
  if (values.length > 0) {
    params[key] = values.join(',');
  }
  return params;
}

/** 将多选值转为 API 传参（无选中返回 null） */
export function toCsvFilterValue(value) {
  const values = normalizeMultiFilterArray(value);
  return values.length > 0 ? values.join(',') : null;
}

/** 剔除已不在下拉选项中的选中值 */
export function pruneMultiSelection(selected, options, getOptionValue) {
  const selectedValues = normalizeMultiFilterArray(selected);
  return selectedValues.filter((value) =>
    options.some((option) => getOptionValue(option) === value)
  );
}

/** 多选模式下清空字段的初始值 */
export function emptyMultiFilterValue(multiSelect) {
  return multiSelect ? [] : '';
}
