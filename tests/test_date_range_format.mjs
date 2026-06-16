/**
 * 广告数据日期范围工具测试
 * 运行: node tests/test_date_range_format.mjs
 */
import assert from 'node:assert/strict';
import {
  getDefaultMonthDateRange,
  getMonthDateRangeForDate,
  isSameDateRange,
  resolveInitialAdDataDateRange
} from '../frontend/src/utils/dateRangeFormat.js';

{
  const [start, end] = getMonthDateRangeForDate('2026-06-16');
  assert.equal(start, '2026-06-01');
  assert.equal(end, '2026-06-30');
}

{
  const range = resolveInitialAdDataDateRange('2025-12-01', '2026-05-31');
  const [monthStart, monthEnd] = getDefaultMonthDateRange();
  if (monthStart <= '2026-05-31' && monthEnd >= '2025-12-01') {
    assert.deepEqual(range, [monthStart, monthEnd]);
  } else {
    assert.deepEqual(range, getMonthDateRangeForDate('2026-05-31'));
  }
}

{
  assert.equal(isSameDateRange(['2025-12-01', '2026-06-16'], ['2025-12-01', '2026-06-16']), true);
  assert.equal(isSameDateRange(['2025-12-01', '2026-06-16'], ['2025-12-01', '2026-06-15']), false);
}

console.log('test_date_range_format.mjs: 全部通过');
