/**
 * 会话管理 API：在线用户会话查询与踢出
 * @file api/session.js
 */
import { request } from '../utils/api';
import {
  withCsrfMutate,
  CSRF_REFRESH_SESSIONS
} from '../utils/csrfMutate';

const CSRF_BLACKLIST = '/api/v1/sessions/blacklist';

export const getMySessions = async (params = {}) =>
  request(
    { url: '/api/v1/sessions/me/sessions', method: 'get', params },
    { paginated: true }
  );

/**
 * revokeMySession 接口。
 */
export const revokeMySession = async (sessionId) =>
  withCsrfMutate(
    () =>
      request(
        {
          url: `/api/v1/sessions/me/sessions/${sessionId}/revoke`,
          method: 'post'
        },
        { returnDataOnly: true }
      ),
    CSRF_REFRESH_SESSIONS
  );

/**
 * revokeAllMySessions 接口。
 */
export const revokeAllMySessions = async () =>
  withCsrfMutate(
    () =>
      request(
        { url: '/api/v1/sessions/me/sessions/revoke-all', method: 'post' },
        { returnDataOnly: true }
      ),
    CSRF_REFRESH_SESSIONS
  );

/**
 * 获取指定用户的活跃会话列表。
 */
export const getUserSessions = async (userId, params = {}) =>
  request(
    {
      url: `/api/v1/sessions/users/${userId}/sessions`,
      method: 'get',
      params
    },
    { paginated: true }
  );

/**
 * revokeUserSession 接口。
 */
export const revokeUserSession = async (userId, sessionId) =>
  withCsrfMutate(
    () =>
      request(
        {
          url: `/api/v1/sessions/users/${userId}/sessions/${sessionId}/revoke`,
          method: 'post'
        },
        { returnDataOnly: true }
      ),
    CSRF_BLACKLIST
  );

/**
 * revokeAllUserSessions 接口。
 */
export const revokeAllUserSessions = async (userId) =>
  withCsrfMutate(
    () =>
      request(
        {
          url: `/api/v1/sessions/users/${userId}/sessions/revoke-all`,
          method: 'post'
        },
        { returnDataOnly: true }
      ),
    CSRF_BLACKLIST
  );

/**
 * 获取会话黑名单列表。
 */
export const getBlacklist = async (params = {}) =>
  request(
    { url: '/api/v1/sessions/blacklist', method: 'get', params },
    { paginated: true }
  );
