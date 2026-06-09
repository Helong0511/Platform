/**
 * 工具模块 - 用户-客户关联判断工具
 * @file utils/userClient.js
 */
import { logger } from './logger';

/**
 * 从用户行解析客户 ID；必要时拉取详情并回写 user.client。
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
      if (userDetail.api_enabled !== undefined) {
        user.api_enabled = userDetail.api_enabled;
      }
      if (userDetail.password_change_enabled !== undefined) {
        user.password_change_enabled = userDetail.password_change_enabled;
      }
      return userDetail.client.id;
    }
  } catch (error) {
    logger.error('获取用户详情失败:', error);
  }
  return null;
}

/**
 * 确认User Has Client。
 */
export async function ensureUserHasClient(user, getUserDetail, ElMessage) {
  if (user.role !== 'client') {
    return false;
  }
  if (user.client?.id) {
    return true;
  }
  try {
    const userData = await getUserDetail(user.id);
    if (userData?.client?.id) {
      user.client = userData.client;
      return true;
    }
    ElMessage.warning('该客户用户还没有关联的客户信息，请先编辑用户并创建客户信息');
    return false;
  } catch (error) {
    return false;
  }
}
