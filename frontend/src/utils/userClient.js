/**
 * 工具模块 - 用户-客户关联判断工具
 * @file utils/userClient.js
 */
import { logger } from './logger';

/**
 * 从用户行解析客户 ID；必要时拉取详情并回写 user.client。
 * @param {Object} user 用户对象
 * @param {Function} getUserDetail 拉取用户详情
 * @returns {Promise<number|null>} 客户 ID
 */
export async function resolveClientIdForUser(user, getUserDetail) {
  if (user.role !== 'client') {
    return null;
  }
  if (user.client?.id) {
    return user.client.id;
  }
  if (user.client_id) {
    if (!user.client) {
      user.client = {};
    }
    user.client.id = user.client_id;
    return user.client_id;
  }
  try {
    const userDetail = await getUserDetail(user.id);
    if (userDetail?.client?.id) {
      if (!user.client) {
        user.client = {};
      }
      user.client.id = userDetail.client.id;
      if (userDetail.client.company_name !== undefined) {
        user.client.company_name = userDetail.client.company_name;
      }
      if (userDetail.api_enabled !== undefined) {
        user.api_enabled = userDetail.api_enabled;
      }
      if (userDetail.password_change_enabled !== undefined) {
        user.password_change_enabled = userDetail.password_change_enabled;
      }
      return userDetail.client.id;
    }
    // 详情偶发只有顶层 client_id
    if (userDetail?.client_id) {
      if (!user.client) {
        user.client = {};
      }
      user.client.id = userDetail.client_id;
      return userDetail.client_id;
    }
  } catch (error) {
    logger.error('获取用户详情失败:', error);
  }
  return null;
}

/**
 * 确认用户已关联客户；内部复用 resolveClientIdForUser，避免两套判定口径。
 * @param {Object} user 用户对象
 * @param {Function} getUserDetail 拉取用户详情
 * @param {{ warning: Function }} ElMessage 消息组件
 * @returns {Promise<boolean>}
 */
export async function ensureUserHasClient(user, getUserDetail, ElMessage) {
  if (user.role !== 'client') {
    return false;
  }
  const clientId = await resolveClientIdForUser(user, getUserDetail);
  if (clientId) {
    return true;
  }
  ElMessage.warning('该客户用户还没有关联的客户信息，请先编辑用户并创建客户信息');
  return false;
}
