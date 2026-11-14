/**
 * 每日统计：按日期 + 用户插入小计行
 * @file utils/dailyReportSubtotals.js
 */

/** 小计行标记字段，合计行计算时需排除 */
export const USER_DATE_SUBTOTAL_FLAG = '_isUserDateSubtotal';

function round2(value) {
  return Math.round((Number(value) || 0) * 100) / 100;
}

function round4(value) {
  return Math.round((Number(value) || 0) * 10000) / 10000;
}

/**
 * 将多行广告指标汇总为一条（比率按合计重算，与表格底部合计逻辑一致）
 * @param {Array<Object>} rows
 * @param {{ cpcSummaryMode?: 'weighted'|'sum', isAdmin?: boolean }} [options]
 */
export function aggregateAdDataMetrics(rows, options = {}) {
  const { cpcSummaryMode = 'sum', isAdmin = false } = options;
  const totals = {
    request_count: 0,
    match_count: 0,
    display_count: 0,
    click_count: 0,
    pageviews: 0,
    revenue_after_deduct: 0,
    revenue_before_deduct: 0,
    cpcSum: 0,
    viewabilityWeighted: 0,
    viewabilityWeight: 0
  };

  for (const row of rows) {
    totals.request_count += Number(row.request_count) || 0;
    totals.match_count += Number(row.match_count) || 0;
    totals.display_count += Number(row.display_count) || 0;
    totals.click_count += Number(row.click_count) || 0;
    totals.pageviews += Number(row.pageviews) || 0;
    totals.revenue_after_deduct += Number(row.revenue_after_deduct) || 0;
    totals.revenue_before_deduct += Number(row.revenue_before_deduct) || 0;
    totals.cpcSum += Number(row.cpc) || 0;

    const viewabilityRate = Number(row.viewability_rate) || 0;
    const clickCount = Number(row.click_count) || 0;
    if (viewabilityRate > 0 && clickCount > 0) {
      totals.viewabilityWeighted += viewabilityRate * clickCount;
      totals.viewabilityWeight += clickCount;
    }
  }

  const coverageRate =
    totals.request_count > 0 ? (totals.match_count / totals.request_count) * 100 : 0;
  const displayRate =
    totals.match_count > 0 ? (totals.display_count / totals.match_count) * 100 : 0;
  const clickRate =
    totals.display_count > 0 ? (totals.click_count / totals.display_count) * 100 : 0;
  const viewabilityRate =
    totals.viewabilityWeight > 0 ? totals.viewabilityWeighted / totals.viewabilityWeight : 0;
  const ecpmAfter =
    totals.display_count > 0
      ? (totals.revenue_after_deduct / totals.display_count) * 1000
      : 0;
  const ecpmBefore =
    totals.display_count > 0
      ? (totals.revenue_before_deduct / totals.display_count) * 1000
      : 0;

  const cpcRevenue = isAdmin ? totals.revenue_before_deduct : totals.revenue_after_deduct;
  const cpc = cpcSummaryMode === 'sum'
    ? totals.cpcSum
    : totals.click_count > 0
      ? cpcRevenue / totals.click_count
      : 0;

  return {
    request_count: totals.request_count,
    match_count: totals.match_count,
    display_count: totals.display_count,
    click_count: totals.click_count,
    pageviews: totals.pageviews,
    revenue_after_deduct: round4(totals.revenue_after_deduct),
    revenue_before_deduct: round4(totals.revenue_before_deduct),
    coverage_rate: round2(coverageRate),
    display_rate: round2(displayRate),
    click_rate: round2(clickRate),
    viewability_rate: round2(viewabilityRate),
    ecpm_after_deduct: round4(ecpmAfter),
    ecpm_before_deduct: round4(ecpmBefore),
    cpc: round2(cpc)
  };
}

/** 日期 + 用户分组键（优先 client_id，便于管理员多客户场景） */
export function getUserDateGroupKey(row) {
  const userKey =
    row.client_id != null && row.client_id !== ''
      ? `c:${row.client_id}`
      : `u:${row.user_name || ''}`;
  return `${row.date || ''}|${userKey}`;
}

/**
 * 按日期、用户排序后，在每个分组末尾插入小计行
 * @param {Array<Object>} rows
 * @param {{ enable?: boolean, dateSortOrder?: 'asc'|'desc', isAdmin?: boolean, cpcSummaryMode?: 'weighted'|'sum' }} [options]
 */
export function injectUserDateSubtotals(rows, options = {}) {
  const {
    enable = true,
    dateSortOrder = 'desc',
    isAdmin = false,
    cpcSummaryMode = 'sum'
  } = options;

  if (!enable || !Array.isArray(rows) || rows.length === 0) {
    return rows ? [...rows] : [];
  }

  const dir = dateSortOrder === 'asc' ? 1 : -1;
  const sorted = [...rows].sort((a, b) => {
    const dateCmp = String(a.date || '').localeCompare(String(b.date || '')) * dir;
    if (dateCmp !== 0) {
      return dateCmp;
    }
    const userA = String(a.user_name || a.client_id || '');
    const userB = String(b.user_name || b.client_id || '');
    return userA.localeCompare(userB, 'zh-CN');
  });

  const result = [];
  let buffer = [];
  let currentKey = null;

  const flushGroup = () => {
    if (buffer.length === 0) {
      return;
    }
    result.push(...buffer);
    const subtotal = buildUserDateSubtotalRow(buffer, { isAdmin, cpcSummaryMode });
    result.push(subtotal);
    buffer = [];
  };

  for (const row of sorted) {
    const key = getUserDateGroupKey(row);
    if (currentKey !== null && key !== currentKey) {
      flushGroup();
    }
    currentKey = key;
    buffer.push(row);
  }
  flushGroup();

  return result;
}

function buildUserDateSubtotalRow(buffer, options) {
  const first = buffer[0];
  const metrics = aggregateAdDataMetrics(buffer, options);
  return {
    ...metrics,
    [USER_DATE_SUBTOTAL_FLAG]: true,
    id: 0,
    date: first.date,
    user_name: first.user_name || '',
    client_id: first.client_id,
    client_name: first.client_name || '',
    product_name: '小计',
    ad_unit: '',
    country_code: 'ZZ',
    country_name_zh: ''
  };
}

/** 过滤小计行，供表格底部合计使用 */
export function excludeUserDateSubtotalRows(rows) {
  if (!Array.isArray(rows)) {
    return [];
  }
  return rows.filter((row) => !row[USER_DATE_SUBTOTAL_FLAG]);
}
