/**
 * 产品管理 API（标准 CRUD + 分配历史等扩展）
 */
import { createCrudApi } from '@/utils/crudApi';
import { request, extractErrorMessage, handleError } from '../utils/api';
import {
  withCsrfMutate,
  handleCsrf403IfNeeded,
  CSRF_REFRESH_PRODUCTS
} from '../utils/csrfMutate';
import { ElMessage } from 'element-plus';

const {
  getProductList,
  getProductDetail: fetchProductDetail,
  createProduct,
  updateProduct,
  deleteProduct
} = createCrudApi('/api/v1/products', {
  methodNames: {
    list: 'getProductList',
    get: 'getProductDetail',
    create: 'createProduct',
    update: 'updateProduct',
    delete: 'deleteProduct'
  },
  csrfOnMutate: true,
  csrfEndpoint: CSRF_REFRESH_PRODUCTS
});

export { getProductList, createProduct, updateProduct, deleteProduct };

export const getProductDetail = async (id, options = {}) => {
  const { silent = false } = options;
  return fetchProductDetail(id, { silent, timeout: 10000 });
};

export const getAvailableProductNames = async (excludeClientId = null, search = null) => {
  try {
    const params = {};
    if (excludeClientId) params.exclude_client_id = excludeClientId;
    if (search) params.search = search;

    const normalized = await request({
      url: '/api/v1/products/available-names',
      method: 'get',
      params
    }, { returnDataOnly: false });

    return {
      data: normalized.data || [],
      count: normalized.count || 0
    };
  } catch {
    return { data: [], count: 0 };
  }
};

export const getProductAssignments = async (productId) => {
  try {
    return await request({
      url: `/api/v1/product-assignments/products/${productId}/assignments`,
      method: 'get'
    }, { returnDataOnly: true, timeout: 30000 });
  } catch (error) {
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      ElMessage.error('请求超时，请稍后重试。如果问题持续，请联系管理员。');
    }
    throw error;
  }
};

export const getClientAssignments = async (clientId) => {
  return request({
    url: `/api/v1/product-assignments/clients/${clientId}/assignments`,
    method: 'get'
  }, { returnDataOnly: true });
};

export const updateAssignmentDates = (assignmentId, dateUpdate) =>
  withCsrfMutate(
    () =>
      request(
        {
          url: `/api/v1/product-assignments/assignments/${assignmentId}/dates`,
          method: 'put',
          data: dateUpdate
        },
        { returnDataOnly: true, timeout: 30000 }
      ),
    CSRF_REFRESH_PRODUCTS
  );

export const batchUpdateAssignmentDates = async (updates) => {
  try {
    return await withCsrfMutate(
      () =>
        request(
          {
            url: '/api/v1/product-assignments/assignments/batch-update-dates',
            method: 'put',
            data: { updates }
          },
          { returnDataOnly: true, timeout: 60000 }
        ),
      CSRF_REFRESH_PRODUCTS
    );
  } catch (error) {
    if (
      !handleCsrf403IfNeeded(error, { extractErrorMessage, handleError, ElMessage })
    ) {
      const errorMsg = extractErrorMessage(error);
      handleError(error, {
        customErrorHandler: () => {
          ElMessage.error(errorMsg || '批量更新失败，请稍后重试');
        }
      });
    }
    throw error;
  }
};
