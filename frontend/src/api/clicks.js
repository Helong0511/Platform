/**
 * 点击日志 API：短链接访问记录查询
 * @file api/clicks.js
 */
import { createCrudApi } from '@/utils/crudApi';
import { request } from '@/utils/api';
import { withCsrfMutate } from '@/utils/csrfMutate';

const { getClicks, getClickDetail } = createCrudApi('/api/v1/clicks', {
  methodNames: {
    list: 'getClicks',
    get: 'getClickDetail'
  },
  include: ['list', 'get'],
  listOptions: { timeout: 45000 }
});

/** 分页获取点击日志列表 */
export { getClicks, getClickDetail };

/**
 * 补发指定点击记录的 Facebook CAPI 上报
 * @param {number|string} clickRecordId - 点击记录 ID
 * @returns {Promise<Object>} 上报结果
 */
export function resendClickFacebookReport(clickRecordId) {
  return withCsrfMutate(() =>
    request(
      {
        url: `/api/v1/clicks/${clickRecordId}/facebook-report`,
        method: 'post'
      },
      { returnDataOnly: true }
    )
  );
}
