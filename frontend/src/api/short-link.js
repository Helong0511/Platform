/**
 * 短链接管理 API
 *
 * 职责：短链接 CRUD、详情/统计、短码校验与自动生成。
 * @file api/short-link.js
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

/** 短链接 CRUD：列表、新建、更新、删除 */
export { getShortLinks, createShortLink, updateShortLink, deleteShortLink };

/**
 * 获取短链接详情（含关联 Offer/渠道等扩展字段）。
 */
export const getShortLinkDetail = async (linkId) => {
  return request({
    url: `/api/v1/short-links/${linkId}/detail`,
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 获取短链接汇总统计（总数、激活数等）。
 */
export const getShortLinkStats = async () => {
  return request({
    url: '/api/v1/short-links/stats/summary',
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 校验短码是否已被占用。
 */
export const checkShortCode = async (shortCode) => {
  return request({
    url: `/api/v1/short-links/check-code/${shortCode}`,
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 由服务端生成可用短码。
 */
export const generateShortCode = async () => {
  return request({
    url: '/api/v1/short-links/generate-code',
    method: 'get'
  }, { returnDataOnly: true });
};
