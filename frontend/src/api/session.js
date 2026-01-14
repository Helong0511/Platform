/**
 * 会话管理API模块
 * 
 * 提供会话和黑名单相关的所有API调用方法，包括：
 * - 获取当前用户的会话列表
 * - 撤销指定会话
 * - 撤销所有其他会话
 * - 获取指定用户的会话（管理员）
 * - 撤销指定用户的会话（管理员）
 * - 获取Token黑名单列表（管理员）
 * 
 * 所有方法都包含完整的错误处理和CSRF令牌管理
 * 
 * @module api/session
 */

/**
 * 会话管理 API
 * 已统一使用 request 函数，保持代码一致性
 */
import { request, refreshCsrfTokenBeforeRequest } from '../utils/api';

/**
 * 获取当前用户的活跃会话列表
 * 
 * @param {Object} params - 查询参数对象
 * @param {number} params.page - 页码，从1开始，默认1
 * @param {number} params.page_size - 每页条数，默认10
 * 
 * @returns {Promise<Object>} 返回标准化的分页响应对象
 * @returns {Object} 返回对象结构：
 *   - data: {Array<Object>} 会话列表数组
 *   - total: {number} 总记录数
 *   - page: {number} 当前页码
 *   - page_size: {number} 每页条数
 *   - total_pages: {number} 总页数
 * 
 * @example
 * const result = await getMySessions({ page: 1, page_size: 10 });
 * console.log(result.data); // 会话列表
 */
export const getMySessions = async (params = {}) => {
  return request({
    url: '/api/v1/sessions/me/sessions',
    method: 'get',
    params
  }, { paginated: true });
};

/**
 * 撤销当前用户的指定会话
 * 
 * @param {number} sessionId - 会话ID
 * @returns {Promise<Object>} 撤销结果
 */
export const revokeMySession = async (sessionId) => {
  await refreshCsrfTokenBeforeRequest('/api/v1/sessions/me/sessions');
  return request({
    url: `/api/v1/sessions/me/sessions/${sessionId}/revoke`,
    method: 'post'
  }, { returnDataOnly: true });
};

/**
 * 撤销当前用户的所有其他会话（保留当前会话）
 * 
 * @returns {Promise<Object>} 撤销结果，包含撤销的会话数量
 */
export const revokeAllMySessions = async () => {
  await refreshCsrfTokenBeforeRequest('/api/v1/sessions/me/sessions');
  return request({
    url: '/api/v1/sessions/me/sessions/revoke-all',
    method: 'post'
  }, { returnDataOnly: true });
};

/**
 * 获取指定用户的会话列表（管理员）
 * 
 * @param {number} userId - 用户ID
 * @param {Object} params - 查询参数对象
 * @param {number} params.page - 页码，从1开始，默认1
 * @param {number} params.page_size - 每页条数，默认10
 * 
 * @returns {Promise<Object>} 返回标准化的分页响应对象
 */
export const getUserSessions = async (userId, params = {}) => {
  return request({
    url: `/api/v1/sessions/users/${userId}/sessions`,
    method: 'get',
    params
  }, { paginated: true });
};

/**
 * 撤销指定用户的指定会话（管理员）
 * 
 * @param {number} userId - 用户ID
 * @param {number} sessionId - 会话ID
 * @returns {Promise<Object>} 撤销结果
 */
export const revokeUserSession = async (userId, sessionId) => {
  await refreshCsrfTokenBeforeRequest('/api/v1/sessions/blacklist');
  return request({
    url: `/api/v1/sessions/users/${userId}/sessions/${sessionId}/revoke`,
    method: 'post'
  }, { returnDataOnly: true });
};

/**
 * 撤销指定用户的所有会话（管理员）
 * 
 * @param {number} userId - 用户ID
 * @returns {Promise<Object>} 撤销结果，包含撤销的会话数量
 */
export const revokeAllUserSessions = async (userId) => {
  await refreshCsrfTokenBeforeRequest('/api/v1/sessions/blacklist');
  return request({
    url: `/api/v1/sessions/users/${userId}/sessions/revoke-all`,
    method: 'post'
  }, { returnDataOnly: true });
};

/**
 * 获取Token黑名单列表（管理员）
 * 
 * @param {Object} params - 查询参数对象
 * @param {number} params.page - 页码，从1开始，默认1
 * @param {number} params.page_size - 每页条数，默认10
 * @param {number} [params.user_id] - 用户ID（可选，筛选指定用户的黑名单）
 * 
 * @returns {Promise<Object>} 返回标准化的分页响应对象
 * @returns {Object} 返回对象结构：
 *   - data: {Array<Object>} 黑名单列表数组
 *   - total: {number} 总记录数
 *   - page: {number} 当前页码
 *   - page_size: {number} 每页条数
 *   - total_pages: {number} 总页数
 * 
 * @example
 * // 获取所有黑名单记录
 * const result = await getBlacklist({ page: 1, page_size: 20 });
 * 
 * // 获取指定用户的黑名单记录
 * const userBlacklist = await getBlacklist({ page: 1, page_size: 20, user_id: 123 });
 */
export const getBlacklist = async (params = {}) => {
  return request({
    url: '/api/v1/sessions/blacklist',
    method: 'get',
    params
  }, { paginated: true });
};

