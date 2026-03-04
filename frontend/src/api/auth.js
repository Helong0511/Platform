/**
 * 认证API模块
 * 提供登录、登出、令牌刷新等功能
 */
import axios from 'axios';
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
