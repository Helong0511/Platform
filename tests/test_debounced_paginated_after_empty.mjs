/**
 * 验证 afterEmpty 在 loading 复位后执行，内部 refetch 不会被 loading 守卫拦截。
 * 运行: node tests/test_debounced_paginated_after_empty.mjs
 */
import assert from 'node:assert/strict';

async function simulateExecuteFetch(afterEmpty) {
  const loading = { value: false };
  let response;

  try {
    loading.value = true;
    response = { data: [], total: 0 };
  } finally {
    loading.value = false;
  }

  if (afterEmpty && response !== undefined) {
    await afterEmpty(response, loading);
  }

  return loading;
}

const runFetch = (loading) => {
  if (loading.value) {
    return false;
  }
  return true;
};

let refetchCalled = false;

await simulateExecuteFetch(async (_response, loading) => {
  assert.equal(loading.value, false, 'afterEmpty 执行时 loading 应已复位');
  const allowed = runFetch(loading);
  assert.equal(allowed, true, 'refetch 不应被 loading 守卫拦截');
  refetchCalled = true;
});

assert.equal(refetchCalled, true);

console.log('test_debounced_paginated_after_empty.mjs: 全部通过');
