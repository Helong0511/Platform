/**
 * 第三方上报日志 API
 * @file api/third-party-report.js
 *
 * 查询 CAPI/像素等第三方上报记录，支持状态更新与汇总统计。
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

/** 第三方上报记录：列表、详情、状态更新 */
export { getThirdPartyReports, getThirdPartyReport, updateThirdPartyReport };

/**
 * 获取第三方上报记录汇总统计。
 */
export const getThirdPartyReportStats = async (params = {}) => {
  return request({
    url: '/api/v1/third-party-reports/stats/summary',
    method: 'get',
    params
  }, { returnDataOnly: true });
};

/**
 * retryThirdPartyReport 接口。
 */
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
