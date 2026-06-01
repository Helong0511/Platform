/**
 * 第三方上报日志 API
 */
import { createCrudApi } from '@/utils/crudApi';
import { request } from '../utils/api';
import { withCsrfMutate } from '../utils/csrfMutate';

const { getThirdPartyReports, getThirdPartyReport, updateThirdPartyReport } = createCrudApi(
  '/api/v1/third-party-reports',
  {
    methodNames: {
      list: 'getThirdPartyReports',
      get: 'getThirdPartyReport',
      update: 'updateThirdPartyReport'
    },
    include: ['list', 'get', 'update'],
    listOptions: { timeout: 45000 },
    csrfOnMutate: true
  }
);

export { getThirdPartyReports, getThirdPartyReport, updateThirdPartyReport };

export const getThirdPartyReportStats = async (params = {}) => {
  return request({
    url: '/api/v1/third-party-reports/stats/summary',
    method: 'get',
    params
  }, { returnDataOnly: true });
};

export const retryThirdPartyReport = async (logId) =>
  withCsrfMutate(() =>
    request(
      {
        url: `/api/v1/third-party-reports/${logId}/retry`,
        method: 'post'
      },
      { returnDataOnly: true }
    )
  );
