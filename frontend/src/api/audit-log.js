/**
 * 审计日志 API：操作记录查询与导出
 * @file api/audit-log.js
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

/** 审计日志查询：分页列表与单条详情 */
export { getAuditLogs, getAuditLog };

/**
 * 获取审计日志汇总统计（按日期范围）。
 */
export const getAuditLogStats = async (params) => {
  return request({
    url: '/api/v1/audit-logs/stats/summary',
    method: 'get',
    params
  }, { returnDataOnly: true });
};

/**
 * 清除全部操作日志（TRUNCATE + 重置自增，仅管理员）。
 */
export const clearAllAuditLogs = async () => {
  return request({
    url: '/api/v1/audit-logs/clear-all',
    method: 'delete'
  }, { returnDataOnly: true });
};
