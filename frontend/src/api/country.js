/**
 * 国家信息维护 API（对接 /api/v1/countries）
 */
import { createCrudApi } from '@/utils/crudApi';
import { request } from '../utils/api';

const {
  getCountries,
  getCountry,
  createCountry,
  updateCountry,
  deleteCountry
} = createCrudApi('/api/v1/countries', {
  resourceName: 'Country',
  methodNames: {
    list: 'getCountries',
    get: 'getCountry',
    create: 'createCountry',
    update: 'updateCountry',
    delete: 'deleteCountry'
  },
  csrfOnMutate: true
});

export {
  getCountries,
  getCountry,
  createCountry,
  updateCountry,
  deleteCountry
};

/** 收集业务数据中未在 countries 表登记的国家代码 */
export const getUnrecognizedCountryCodes = () =>
  request(
    { url: '/api/v1/countries/unrecognized', method: 'get' },
    { returnDataOnly: true }
  );

/** 国家英文别名列表 */
export const getCountryAliases = (params = {}) =>
  request(
    { url: '/api/v1/countries/aliases', method: 'get', params },
    { returnDataOnly: true }
  );

/** 创建国家英文别名 */
export const createCountryAlias = (data) =>
  request(
    { url: '/api/v1/countries/aliases', method: 'post', data },
    { returnDataOnly: true, csrf: true }
  );

/** 删除国家英文别名 */
export const deleteCountryAlias = (aliasId) =>
  request(
    { url: `/api/v1/countries/aliases/${aliasId}`, method: 'delete' },
    { returnDataOnly: true, csrf: true }
  );
