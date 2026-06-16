/**
 * 每日统计小计行工具单元测试
 * 运行: node tests/test_daily_report_subtotals.mjs
 */
import assert from 'node:assert/strict';
import {
  aggregateAdDataMetrics,
  getUserDateGroupKey,
  injectUserDateSubtotals,
  USER_DATE_SUBTOTAL_FLAG,
  excludeUserDateSubtotalRows
} from '../frontend/src/utils/dailyReportSubtotals.js';

function makeRow(overrides = {}) {
  return {
    date: '2026-06-01',
    user_name: '客户A',
    client_id: 1,
    product_name: '产品1',
    request_count: 100,
    match_count: 80,
    display_count: 50,
    click_count: 10,
    viewability_rate: 60,
    cpc: 1.5,
    pageviews: 200,
    revenue_after_deduct: 25,
    revenue_before_deduct: 30,
    ...overrides
  };
}

// aggregateAdDataMetrics
{
  const agg = aggregateAdDataMetrics([makeRow(), makeRow({ product_name: '产品2', request_count: 200, match_count: 100, display_count: 50, click_count: 5, revenue_after_deduct: 15 })]);
  assert.equal(agg.request_count, 300);
  assert.equal(agg.match_count, 180);
  assert.equal(agg.display_count, 100);
  assert.equal(agg.click_count, 15);
  assert.equal(agg.revenue_after_deduct, 40);
  assert.equal(agg.coverage_rate, 60);
}

// getUserDateGroupKey
{
  assert.equal(getUserDateGroupKey(makeRow()), '2026-06-01|c:1');
  assert.notEqual(
    getUserDateGroupKey(makeRow()),
    getUserDateGroupKey(makeRow({ date: '2026-06-02' }))
  );
}

// injectUserDateSubtotals：两个产品同一日期同一用户 → 明细 + 小计
{
  const rows = [
    makeRow({ product_name: '产品1' }),
    makeRow({ product_name: '产品2', request_count: 50 })
  ];
  const injected = injectUserDateSubtotals(rows);
  assert.equal(injected.length, 3);
  assert.equal(injected[2][USER_DATE_SUBTOTAL_FLAG], true);
  assert.equal(injected[2].product_name, '小计');
  assert.equal(injected[2].request_count, 150);
}

// 不同日期各一条小计
{
  const rows = [
    makeRow({ date: '2026-06-02', product_name: 'P2' }),
    makeRow({ date: '2026-06-01', product_name: 'P1' })
  ];
  const injected = injectUserDateSubtotals(rows, { dateSortOrder: 'desc' });
  assert.equal(injected.length, 4);
  assert.equal(injected[0].date, '2026-06-02');
  assert.equal(injected[1].product_name, '小计');
  assert.equal(injected[2].date, '2026-06-01');
  assert.equal(injected[3].product_name, '小计');
}

// excludeUserDateSubtotalRows
{
  const injected = injectUserDateSubtotals([makeRow(), makeRow({ product_name: 'P2' })]);
  assert.equal(excludeUserDateSubtotalRows(injected).length, 2);
}

// enable=false 不插入
{
  const injected = injectUserDateSubtotals([makeRow(), makeRow({ product_name: 'P2' })], { enable: false });
  assert.equal(injected.length, 2);
}

console.log('test_daily_report_subtotals.mjs: 全部通过');
