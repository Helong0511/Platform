/**
 * 转化扣量配置 API（/api/v1/conversion-deductions）。
 *
 * CRUD 扣量规则，以及扣量日志查询、手动触发扣量等管理端接口。
 */
import { request } from '@/utils/api';
import { createCrudApi } from '@/utils/crudApi';
import { withCsrfMutate } from '@/utils/csrfMutate';

const {
  getDeductionConfigs,
  createDeductionConfig,
  updateDeductionConfig,
  deleteDeductionConfig
} = createCrudApi('/api/v1/conversion-deductions', {
  listTrailingSlash: false,
  csrfOnMutate: true,
  include: ['list', 'create', 'update', 'delete'],
  methodNames: {
    list: 'getDeductionConfigs',
    create: 'createDeductionConfig',
    update: 'updateDeductionConfig',
    delete: 'deleteDeductionConfig'
  }
});

/** 扣量配置 CRUD 方法（列表/新建/更新/删除） */
export {
  getDeductionConfigs,
  createDeductionConfig,
  updateDeductionConfig,
  deleteDeductionConfig
};

/**
 * 切换单条扣量规则的启用状态
 * @param {number|string} id - 扣量配置 ID
 * @param {boolean} isActive - 是否启用
 * @returns {Promise<Object>}
 */
export function updateDeductionConfigStatus(id, isActive) {
  return withCsrfMutate(() =>
    request(
      {
        url: `/api/v1/conversion-deductions/${id}/status`,
        method: 'patch',
        data: { is_active: isActive }
      },
      { returnDataOnly: true }
    )
  );
}

/**
 * 获取扣量统计数据
 * @param {Object} params - 筛选参数
 * @returns {Promise<Object>}
 */
export function getDeductionStats(params) {
  return request({
    url: '/api/v1/conversion-deductions/stats',
    method: 'get',
    params
  }, { returnDataOnly: true });
}

/**
 * 分页获取扣量执行日志
 * @param {Object} params - 分页与筛选参数
 * @returns {Promise<Object>} 分页结果
 */
export function getDeductionLogs(params) {
  return request({
    url: '/api/v1/conversion-deductions/logs',
    method: 'get',
    params
  }, { paginated: true });
}

/**
 * 批量更新扣量规则启用状态
 * @param {Object} data - 包含 ids 与 is_active 的请求体
 * @returns {Promise<Object>}
 */
export function batchUpdateDeductionConfigStatus(data) {
  return withCsrfMutate(() =>
    request(
      {
        url: '/api/v1/conversion-deductions/batch/update-status',
        method: 'post',
        data
      },
      { returnDataOnly: true }
    )
  );
}

/**
 * 批量删除扣量配置
 * @param {Object} data - 包含待删除 ID 列表的请求体
 * @returns {Promise<Object>}
 */
export function batchDeleteDeductionConfigs(data) {
  return withCsrfMutate(() =>
    request(
      {
        url: '/api/v1/conversion-deductions/batch/delete',
        method: 'post',
        data
      },
      { returnDataOnly: true }
    )
  );
}
