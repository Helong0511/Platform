/**
 * 客户开放 API 相关接口
 * @file api/client-api.js
 */
import { request } from '../utils/api';

/** 获取当前登录客户的 API 密钥（按需） */
export const getClientApiKey = (options = {}) =>
  request(
    { url: '/api/v1/client/api-key', method: 'get' },
    { returnDataOnly: true, silent: true, ...options }
  );
