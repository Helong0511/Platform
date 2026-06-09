/**
 * 认证 API 模块
 * @file api/auth.js
 *
 * 提供 OAuth2 密码模式登录、令牌刷新、登出等接口。
 * 登录接口不走标准 { code, data } 包装，需单独解析响应。
 */
import axios from 'axios';
import { request } from '../utils/api';
import { parseAuthResponseData } from '../utils/authResponse';

/**
 * OAuth2 密码模式登录（application/x-www-form-urlencoded）
 * 登录接口不走标准 { code, data } 包装，返回 LoginResponse
 * @param {string} username - 用户名
 * @param {string} password - 密码
 * @param {Object} [options]
 * @param {number} [options.timeout] - 超时毫秒
 * @returns {Promise<Object>} { access_token, token_type, refresh_token, user }
 */
/**
 * loginOAuth2 接口。
 */
export const loginOAuth2 = async (username, password, options = {}) => {
  const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  const timeout = options.timeout ?? (isMobile ? 30000 : 15000);

  const response = await axios.post(
    '/api/v1/auth/login',
    new URLSearchParams({
      username,
      password,
      grant_type: 'password'
    }),
    {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      timeout
    }
  );

  const payload = parseAuthResponseData(response.data);
  if (!payload.user) {
    throw new Error('登录响应数据格式错误：缺少用户信息');
  }
  return payload;
};

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
 * 用户登录（JSON 体，供非 OAuth2 场景；管理端登录请用 loginOAuth2）
 */
export const login = async (username, password) => {
  return loginOAuth2(username, password);
};

/**
 * 用户登出
 * @returns {Promise<Object>} 登出响应
 */
export const logout = async () => {
  return request({
    url: '/api/v1/auth/logout',
    method: 'post'
  }, { returnDataOnly: true, silent: true });
};
