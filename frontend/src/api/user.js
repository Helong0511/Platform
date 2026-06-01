/**
 * 用户管理 API：列表/详情/CRUD、密码、导出、统计
 * @module api/user
 */
import { createCrudApi } from '@/utils/crudApi';
import { request } from '../utils/api';
import { requestListExport } from './helpers/exportDownload';
import { prepareCsrfMutate, CSRF_REFRESH_USERS } from '../utils/csrfMutate';
import { ElMessage } from 'element-plus';
import { getSuccessMessage } from '../utils/messages';

const {
  getUsers,
  getUser: getUserDetail,
  createUser,
  updateUser,
  deleteUser: deleteUserBase
} = createCrudApi('/api/v1/users', {
  methodNames: {
    list: 'getUsers',
    get: 'getUserDetail',
    create: 'createUser',
    update: 'updateUser',
    delete: 'deleteUser'
  },
  csrfOnMutate: true,
  csrfEndpoint: CSRF_REFRESH_USERS
});

export { getUsers, getUserDetail, createUser, updateUser };

export const searchUser = async (searchTerm) => {
  try {
    if (!searchTerm || searchTerm.toString().trim() === '') {
      return null;
    }

    const term = searchTerm.toString().trim();

    if (/^\d+$/.test(term)) {
      try {
        const result = await getUserDetail(term, { silent: true });
        if (result?.id) {
          return result;
        }
      } catch {
        /* 继续按用户名查 */
      }
    }

    const usersData = await request(
      {
        url: '/api/v1/users/',
        method: 'get',
        params: { username: term, page_size: 10 }
      },
      { paginated: true, silent: true }
    );
    if (usersData.data?.length > 0) {
      const exactMatch = usersData.data.find(
        (user) => user.username?.toLowerCase() === term.toLowerCase()
      );
      return exactMatch || usersData.data[0];
    }
    return null;
  } catch {
    return null;
  }
};

/** 获取当前登录用户信息 */
export const getCurrentUserInfo = async () =>
  request({ url: '/api/v1/users/me', method: 'get' }, { returnDataOnly: true });

/** @deprecated 请使用 getCurrentUserInfo */
export const getCurrentUser = getCurrentUserInfo;

export const deleteUser = async (id) => {
  await prepareCsrfMutate(CSRF_REFRESH_USERS);
  await deleteUserBase(id);
  return true;
};

export const exportUsers = (params = {}) =>
  requestListExport(
    { url: '/api/v1/users/export/excel', method: 'get', params },
    {
      defaultFilename: '用户数据.xlsx',
      onSuccess: () => ElMessage.success(getSuccessMessage('USER_EXPORT_SUCCESS'))
    }
  );

export const getUserStats = async () => {
  return request({
    url: '/api/v1/users/stats',
    method: 'get'
  }, { returnDataOnly: true });
};

export const changePassword = async (passwordData) => {
  await prepareCsrfMutate(CSRF_REFRESH_USERS);
  return request(
    {
      url: '/api/v1/users/me/password',
      method: 'put',
      data: passwordData
    },
    { returnDataOnly: true }
  );
};
