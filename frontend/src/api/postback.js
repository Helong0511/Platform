/**
 * Postback 管理 API
 * 已统一使用 request 函数，保持代码一致性
 */
import { request } from '../utils/api';

/**
 * 获取 Postback 转化记录列表
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页条数
 * @param {string} [params.platform] - 平台名称筛选
 * @param {number} [params.product_id] - 产品ID筛选
 * @param {number} [params.client_id] - 客户ID筛选
 * @param {string} [params.conversion_or_click_id] - 转化ID或点击ID筛选
 * @param {string} [params.start_date] - 开始日期（YYYY-MM-DD）
 * @param {string} [params.end_date] - 结束日期（YYYY-MM-DD）
 * @returns {Promise<Object>} 转化记录列表数据
 */
export const getPostbackConversions = async (params) => {
  return request({
    url: '/api/v1/postback/conversions',
    method: 'get',
    params
  }, { paginated: true });
};

/**
 * 获取 Postback 统计信息
 * @param {Object} params - 查询参数
 * @param {string} [params.platform] - 平台名称筛选
 * @param {string} [params.start_date] - 开始日期（YYYY-MM-DD）
 * @param {string} [params.end_date] - 结束日期（YYYY-MM-DD）
 * @returns {Promise<Array>} 统计信息列表
 */
export const getPostbackStats = async (params = {}) => {
  return request({
    url: '/api/v1/postback/stats',
    method: 'get',
    params
  }, { returnDataOnly: true });
};

/**
 * 更新转化状态（融合转化日志功能）
 * @param {number} conversionId - 转化记录ID
 * @param {string} status - 转化状态（Approved/Pending）
 * @returns {Promise<Object>} 更新结果
 */
export const updateConversionStatus = async (conversionId, status) => {
  return request({
    url: `/api/v1/postback/conversions/${conversionId}/status`,
    method: 'put',
    params: { status }
  }, { returnDataOnly: true });
};

/**
 * 获取 IP 白名单列表
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页条数
 * @param {string} [params.ip_address] - IP地址（模糊搜索）
 * @param {boolean} [params.is_active] - 是否启用
 * @returns {Promise<Object>} IP白名单列表数据
 */
export const getIpWhitelist = async (params) => {
  return request({
    url: '/api/v1/postback/ip-whitelist',
    method: 'get',
    params
  }, { paginated: true });
};

/**
 * 创建 IP 白名单
 * @param {Object} data - IP白名单数据
 * @param {string} data.ip_address - IP地址
 * @param {string} [data.description] - 描述
 * @param {boolean} [data.is_active] - 是否启用
 * @returns {Promise<Object>} 创建的IP白名单数据
 */
export const createIpWhitelist = async (data) => {
  return request({
    url: '/api/v1/postback/ip-whitelist',
    method: 'post',
    data
  }, { returnDataOnly: true });
};

/**
 * 更新 IP 白名单
 * @param {number} id - IP白名单ID
 * @param {Object} data - 更新的数据
 * @param {string} [data.ip_address] - IP地址
 * @param {string} [data.description] - 描述
 * @param {boolean} [data.is_active] - 是否启用
 * @returns {Promise<Object>} 更新的IP白名单数据
 */
export const updateIpWhitelist = async (id, data) => {
  return request({
    url: `/api/v1/postback/ip-whitelist/${id}`,
    method: 'put',
    data
  }, { returnDataOnly: true });
};

/**
 * 删除 IP 白名单
 * @param {number} id - IP白名单ID
 * @returns {Promise<Object>} 删除结果
 */
export const deleteIpWhitelist = async (id) => {
  return request({
    url: `/api/v1/postback/ip-whitelist/${id}`,
    method: 'delete'
  }, { returnDataOnly: true });
};

/**
 * 批量创建 IP 白名单
 * @param {Object} data - 批量创建数据
 * @param {Array<string>} data.ip_addresses - IP地址列表
 * @param {string} [data.description] - 描述（应用于所有IP）
 * @param {boolean} [data.is_active] - 是否启用（应用于所有IP）
 * @returns {Promise<Object>} 批量创建结果
 */
export const batchCreateIpWhitelist = async (data) => {
  return request({
    url: '/api/v1/postback/ip-whitelist/batch',
    method: 'post',
    data
  }, { returnDataOnly: true });
};
