/**
 * 短链接管理 API
 */
import { createCrudApi } from '@/utils/crudApi';
import { request } from '../utils/api';
const {
  getShortLinks,
  createShortLink,
  updateShortLink,
  deleteShortLink
} = createCrudApi('/api/v1/short-links', {
  methodNames: {
    list: 'getShortLinks',
    create: 'createShortLink',
    update: 'updateShortLink',
    delete: 'deleteShortLink'
  },
  csrfOnMutate: true
});

export { getShortLinks, createShortLink, updateShortLink, deleteShortLink };

export const getShortLinkDetail = async (linkId) => {
  return request({
    url: `/api/v1/short-links/${linkId}/detail`,
    method: 'get'
  }, { returnDataOnly: true });
};

export const getShortLinkStats = async () => {
  return request({
    url: '/api/v1/short-links/stats/summary',
    method: 'get'
  }, { returnDataOnly: true });
};

export const checkShortCode = async (shortCode) => {
  return request({
    url: `/api/v1/short-links/check-code/${shortCode}`,
    method: 'get'
  }, { returnDataOnly: true });
};

export const generateShortCode = async () => {
  return request({
    url: '/api/v1/short-links/generate-code',
    method: 'get'
  }, { returnDataOnly: true });
};
