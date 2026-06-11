/**
 * 国家信息维护 API（对接 /api/v1/countries）
 */
import { createCrudApi } from '@/utils/crudApi';

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
