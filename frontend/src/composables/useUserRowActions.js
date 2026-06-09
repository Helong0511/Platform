/**
 * 组合式函数 - 用户行操作：启用/禁用/重置密码
 * @file composables/useUserRowActions.js
 */
import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { deleteUser, updateUser, getUserDetail } from '../api/user';
import { updateClient, updateClientSwitches } from '../api/client';
import { extractErrorMessage, isErrorHandled } from '../utils/api';
import { ensureCsrfToken } from '../utils/csrfMutate';
import { resolveClientIdForUser, ensureUserHasClient } from '../utils/userClient';
import { logger } from '../utils/logger';

/**
 * 用户列表行操作：删除、状态、客户开关、产品、通知配置。
 */
/**
 * 组合式函数 - 用户行操作：启用/禁用/重置密码
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useUserRowActions({
  fetchUsers,
  fetchStats,
  openProductDialog,
}) {
  // notificationConfigDialogVisible 响应式状态
  const notificationConfigDialogVisible = ref(false);
  const currentClientIdForNotification = ref(null);
  // currentClientNameForNotification 响应式状态
  const currentClientNameForNotification = ref('');

  const refreshUsersAndStats = async () => {
    await fetchUsers(true);
    await new Promise((r) => setTimeout(r, 200));
    await fetchStats();
  };

  const handleDelete = async (id) => {
    try {
      await ElMessageBox.confirm('确定要删除该用户吗？此操作不可恢复！', '确认删除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
        appendTo: document.body,
        zIndex: 3001,
      });
      await ensureCsrfToken(() => fetchUsers());
      await deleteUser(id);
      ElMessage.success('用户删除成功');
      await refreshUsersAndStats();
    } catch (error) {
      if (error !== 'cancel' && !isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    }
  };

  const handleStatusChange = async (user) => {
    try {
      const newStatus = !user.is_active;
      const confirmText = newStatus ? '启用' : '禁用';
      await ElMessageBox.confirm(
        `确定要${confirmText}用户 "${user.username}" 吗？`,
        '确认操作',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning',
          appendTo: document.body,
          zIndex: 3001,
        },
      );
      await updateUser(user.id, { is_active: newStatus });
      if (user.role === 'client' && user.client?.id) {
        await updateClient(user.client.id, { is_active: newStatus });
      }
      ElMessage.success(`用户${confirmText}成功`);
      await refreshUsersAndStats();
    } catch (error) {
      if (error !== 'cancel' && !isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    }
  };

  const handleClientSwitchChange = async (user, newValue, field) => {
    if (user.role !== 'client') return;
    const loadingKey = field === 'api_enabled' ? '_apiSwitchLoading' : '_passwordSwitchLoading';
    if (user[loadingKey]) return;

    const oldValue = user[field] || false;
    user[field] = newValue;

    const clientId = await resolveClientIdForUser(user, getUserDetail);
    if (!clientId) {
      ElMessage.warning('客户信息不完整，无法更新开关。请确保该用户已关联客户信息。');
      user[field] = oldValue;
      return;
    }

    user[loadingKey] = true;
    try {
      await ensureCsrfToken(() => fetchUsers());
      const payload =
        field === 'api_enabled'
          ? { api_enabled: newValue }
          : { password_change_enabled: newValue };
      const result = await updateClientSwitches(clientId, payload);
      if (result && result[field] !== undefined) {
        user[field] = Boolean(result[field]);
      }
      const label = field === 'api_enabled' ? 'API访问' : '密码修改权限';
      ElMessage.success(`${label}已${newValue ? '启用' : '禁用'}`);
    } catch (error) {
      logger.error('更新客户开关失败:', error);
      user[field] = oldValue;
    } finally {
      user[loadingKey] = false;
    }
  };

  const handleApiSwitchChange = (user, newValue) =>
    handleClientSwitchChange(user, newValue, 'api_enabled');

  const handlePasswordSwitchChange = (user, newValue) =>
    handleClientSwitchChange(user, newValue, 'password_change_enabled');

  const handleManageProducts = async (user) => {
    if (user.role !== 'client') return;
    if (!(await ensureUserHasClient(user, getUserDetail, ElMessage))) return;
    openProductDialog({
      id: user.client.id,
      full_name: user.full_name || user.username || '未知客户',
    });
  };

  const handleNotificationConfig = async (user) => {
    if (user.role !== 'client') return;
    if (!(await ensureUserHasClient(user, getUserDetail, ElMessage))) return;
    currentClientIdForNotification.value = user.client.id;
    currentClientNameForNotification.value =
      user.full_name || user.username || user.client.company_name || '未知客户';
    notificationConfigDialogVisible.value = true;
  };

  const handleNotificationConfigSaved = () => {
    ElMessage.success('通知配置已保存');
  };

  return {
    notificationConfigDialogVisible,
    currentClientIdForNotification,
    currentClientNameForNotification,
    handleDelete,
    handleStatusChange,
    handleApiSwitchChange,
    handlePasswordSwitchChange,
    handleManageProducts,
    handleNotificationConfig,
    handleNotificationConfigSaved,
  };
}
