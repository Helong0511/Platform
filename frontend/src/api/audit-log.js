/**
 * 操作日志 API（只读列表 + 详情）
 */
import { createCrudApi } from '@/utils/crudApi';
import { request } from '../utils/api';

const { getAuditLogs, getAuditLog } = createCrudApi('/api/v1/audit-logs', {
  methodNames: {
    list: 'getAuditLogs',
    get: 'getAuditLog'
  },
  include: ['list', 'get'],
  listOptions: { timeout: 45000 }
});

export { getAuditLogs, getAuditLog };

export const getAuditLogStats = async (params) => {
  return request({
    url: '/api/v1/audit-logs/stats/summary',
    method: 'get',
    params
  }, { returnDataOnly: true });
};
