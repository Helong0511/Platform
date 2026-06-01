/**
 * 会话管理 API
 * @module api/session
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

export const revokeAllMySessions = async () =>
  withCsrfMutate(
    () =>
      request(
        { url: '/api/v1/sessions/me/sessions/revoke-all', method: 'post' },
        { returnDataOnly: true }
      ),
    CSRF_REFRESH_SESSIONS
  );

export const getUserSessions = async (userId, params = {}) =>
  request(
    {
      url: `/api/v1/sessions/users/${userId}/sessions`,
      method: 'get',
      params
    },
    { paginated: true }
  );

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

export const getBlacklist = async (params = {}) =>
  request(
    { url: '/api/v1/sessions/blacklist', method: 'get', params },
    { paginated: true }
  );
