/**
 * 认证API模块
 * 提供登录、登出、令牌刷新等功能
 */
import { request } from '../utils/api';

/**
 * 刷新访问令牌
 * @param {string} refreshToken - 刷新令牌
 * @returns {Promise<Object>} 新的令牌和用户信息
 */
export const refreshAccessToken = async (refreshToken) => {
  return request({
    url: '/api/v1/auth/refresh',
    method: 'post',
    data: {
      refresh_token: refreshToken
    }
  }, { returnDataOnly: true });
};

/**
 * 用户登录
 * @param {string} username - 用户名
 * @param {string} password - 密码
 * @returns {Promise<Object>} 登录响应，包含令牌和用户信息
 */
export const login = async (username, password) => {
  return request({
    url: '/api/v1/auth/login',
    method: 'post',
    data: {
      username,
      password
    }
  }, { returnDataOnly: true });
};

/**
 * 用户登出
 * @returns {Promise<Object>} 登出响应
 */
export const logout = async () => {
  return request({
    url: '/api/v1/auth/logout',
    method: 'post'
  }, { returnDataOnly: true });
};

/**
 * 获取当前用户信息
 * @returns {Promise<Object>} 用户信息
 */
export const getCurrentUser = async () => {
  return request({
    url: '/api/v1/users/me',
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 修改当前用户密码
 * @param {string} oldPassword - 旧密码
 * @param {string} newPassword - 新密码
 * @returns {Promise<Object>} 修改密码响应
 */
export const changePassword = async (oldPassword, newPassword) => {
  return request({
    url: '/api/v1/users/me/password',
    method: 'put',
    data: {
      old_password: oldPassword,
      new_password: newPassword
    }
  }, { returnDataOnly: true });
};
