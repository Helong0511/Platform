/**
 * 通用CRUD API生成器
 * 自动生成标准的CRUD操作函数，减少重复代码
 * 
 * @module utils/crudApi
 */

import { request } from './api';

/**
 * 首字母大写
 * @param {string} str - 字符串
 * @returns {string} 首字母大写的字符串
 */
function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * 从路径中提取资源名称
 * @param {string} basePath - API基础路径，如 '/api/v1/offers'
 * @returns {string} 资源名称，如 'offer'
 */
function extractResourceName(basePath) {
  const parts = basePath.split('/').filter(p => p);
  const lastPart = parts[parts.length - 1];
  // 处理复数形式，如 'offers' -> 'offer'
  if (lastPart.endsWith('s')) {
    return lastPart.slice(0, -1);
  }
  return lastPart;
}

/**
 * 通用CRUD API生成器
 * 自动生成标准的CRUD操作函数
 * 
 * @param {string} basePath - API基础路径，如 '/api/v1/offers'
 * @param {Object} options - 配置选项
 * @param {Object} options.customMethods - 自定义方法对象，键为方法名，值为函数
 * @param {string} options.resourceName - 资源名称（可选，默认从basePath提取）
 * @param {boolean} options.paginated - 列表接口是否使用分页响应（默认：true）
 * @returns {Object} 包含CRUD方法的对象
 * 
 * @example
 * // 基本使用
 * const offerApi = createCrudApi('/api/v1/offers');
 * // 返回: { getOffers, getOffer, createOffer, updateOffer, deleteOffer }
 * 
 * @example
 * // 带自定义方法
 * const offerApi = createCrudApi('/api/v1/offers', {
 *   customMethods: {
 *     checkOfferShortLink: (id) => {
 *       return request({ url: `/api/v1/offers/${id}/check-short-link`, method: 'get' });
 *     }
 *   }
 * });
 */
export function createCrudApi(basePath, options = {}) {
  const {
    customMethods = {},
    resourceName = null,
    paginated = true
  } = options;

  // 提取资源名称
  const resource = resourceName || extractResourceName(basePath);
  const Resource = capitalize(resource);
  const Resources = capitalize(resource) + 's'; // 简单的复数形式

  // 生成CRUD方法
  const crudMethods = {
    /**
     * 获取列表
     * @param {Object} params - 查询参数
     * @returns {Promise} 响应数据
     */
    [`get${Resources}`]: (params = {}) => {
      return request({
        url: `${basePath}/`,
        method: 'get',
        params
      }, { paginated });
    },

    /**
     * 获取详情
     * @param {number|string} id - 资源ID
     * @returns {Promise} 响应数据
     */
    [`get${Resource}`]: (id) => {
      return request({
        url: `${basePath}/${id}`,
        method: 'get'
      }, { returnDataOnly: true });
    },

    /**
     * 创建资源
     * @param {Object} data - 资源数据
     * @returns {Promise} 响应数据
     */
    [`create${Resource}`]: (data) => {
      return request({
        url: `${basePath}/`,
        method: 'post',
        data
      }, { returnDataOnly: true });
    },

    /**
     * 更新资源
     * @param {number|string} id - 资源ID
     * @param {Object} data - 更新数据
     * @returns {Promise} 响应数据
     */
    [`update${Resource}`]: (id, data) => {
      return request({
        url: `${basePath}/${id}`,
        method: 'put',
        data
      }, { returnDataOnly: true });
    },

    /**
     * 删除资源
     * @param {number|string} id - 资源ID
     * @returns {Promise} 响应数据
     */
    [`delete${Resource}`]: (id) => {
      return request({
        url: `${basePath}/${id}`,
        method: 'delete'
      }, { returnDataOnly: true });
    }
  };

  // 合并自定义方法
  return {
    ...crudMethods,
    ...customMethods
  };
}

/**
 * 批量导出CRUD API
 * 用于一次性生成多个资源的CRUD API
 * 
 * @param {Array<Object>} configs - 配置数组，每个配置包含 basePath 和 options
 * @returns {Object} 包含所有CRUD方法的对象
 * 
 * @example
 * const apis = createMultipleCrudApis([
 *   { basePath: '/api/v1/offers' },
 *   { basePath: '/api/v1/advertisers' },
 *   { basePath: '/api/v1/publishers' }
 * ]);
 * // 返回: { getOffers, getOffer, createOffer, ..., getAdvertisers, ... }
 */
export function createMultipleCrudApis(configs) {
  const result = {};
  
  configs.forEach(config => {
    const { basePath, ...options } = config;
    const api = createCrudApi(basePath, options);
    Object.assign(result, api);
  });
  
  return result;
}
