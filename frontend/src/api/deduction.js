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

export {
  getDeductionConfigs,
  createDeductionConfig,
  updateDeductionConfig,
  deleteDeductionConfig
};

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

export function getDeductionStats(params) {
  return request({
    url: '/api/v1/conversion-deductions/stats',
    method: 'get',
    params
  }, { returnDataOnly: true });
}

export function getDeductionLogs(params) {
  return request({
    url: '/api/v1/conversion-deductions/logs',
    method: 'get',
    params
  }, { paginated: true });
}

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
