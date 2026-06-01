/**
 * 短链接访问记录 API
 */
import { createCrudApi } from '@/utils/crudApi';
import { request } from '@/utils/api';
import { withCsrfMutate } from '@/utils/csrfMutate';

const { getClicks, getClick: getClickDetail } = createCrudApi('/api/v1/clicks', {
  methodNames: {
    list: 'getClicks',
    get: 'getClickDetail'
  },
  include: ['list', 'get'],
  listOptions: { timeout: 45000 }
});

export { getClicks, getClickDetail };

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
