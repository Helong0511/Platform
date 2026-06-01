/**
 * 「有数据的客户/产品/国家」筛选接口工厂（广告数据、TB 搜索等模块共用）
 */
import { request, handleError } from '../../utils/api';

async function fetchWithDataResource(url, params) {
  try {
    const result = await request(
      { url, method: 'get', params },
      { returnDataOnly: false }
    );
    return {
      data: result.data || [],
      count: result.count ?? 0,
      raw: result
    };
  } catch (error) {
    handleError(error);
    return { data: [], count: 0, raw: { data: [], count: 0 } };
  }
}

/**
 * @param {'ad-data'|'tb-search-data'} moduleKey
 * @param {{ returnRaw?: boolean }} [options] returnRaw=true 时返回完整响应体（TB 页历史行为）
 */
export function createWithDataFilterApi(moduleKey, options = {}) {
  const { returnRaw = false } = options;
  const prefix = `/api/v1/${moduleKey}`;

  const pick = (payload) => (returnRaw ? payload.raw : { data: payload.data, count: payload.count });

  return {
    getClientsWithData: async (startDate = null, endDate = null) => {
      const params = {};
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      const payload = await fetchWithDataResource(`${prefix}/clients-with-data`, params);
      return pick(payload);
    },

    getProductsWithData: async (clientId = null, startDate = null, endDate = null) => {
      const params = {};
      if (clientId) params.client_id = clientId;
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      const payload = await fetchWithDataResource(`${prefix}/products-with-data`, params);
      return pick(payload);
    },

    getCountriesWithData: async (
      clientId = null,
      productId = null,
      startDate = null,
      endDate = null
    ) => {
      const params = {};
      if (clientId) params.client_id = clientId;
      if (productId) params.product_id = productId;
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      const payload = await fetchWithDataResource(`${prefix}/countries-with-data`, params);
      return pick(payload);
    }
  };
}
