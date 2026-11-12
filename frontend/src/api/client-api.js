/**
 * 客户开放 API 相关接口
 * @file api/client-api.js
 */
import { request } from '../utils/api';

/** 获取当前登录客户的 API 密钥；多客户账号通过 clientId 明确选择客户主体 */
export const getClientApiKey = (clientId, options = {}) =>
  request(
    {
      url: '/api/v1/client/api-key',
      method: 'get',
      params: clientId == null ? undefined : { client_id: clientId }
    },
    { returnDataOnly: true, silent: true, ...options }
  );
