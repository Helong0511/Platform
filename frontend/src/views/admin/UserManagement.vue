<!--
  管理端 - 用户管理入口
  @file views/admin/UserManagement.vue
-->
<template>
  <div class="user-management-container">
    <UserPageHeader :stats="stats" @add="handleAddUser" />

    <UserFilterBar
      :search-form="searchForm"
      :loading="loading"
      @search="fetchUsers"
      @reset="resetFilter"
    />

    <UserTable
      :users="users"
      :loading="loading"
      :column-visibility="columnVisibility"
      :has-client-users="hasClientUsers"
      :format-date="formatDate"
      :current-user-id="currentUser?.id"
      :is-mobile="isMobile"
      :pagination="pagination"
      @open-column-settings="columnSettingVisible = true"
      @sort-change="handleSortChange"
      @status-change="handleStatusChange"
      @api-switch-change="handleApiSwitchChange"
      @password-switch-change="handlePasswordSwitchChange"
      @view="handleView"
      @edit="handleEdit"
      @manage-products="handleManageProducts"
      @notification-config="handleNotificationConfig"
      @delete="handleDelete"
    />

    <UserColumnSettingDialog
      v-model="columnSettingVisible"
      v-model:column-visibility-array="columnVisibilityArray"
      :has-client-users="hasClientUsers"
      @save="saveColumnVisibility"
    />

    <UserFormDialog
      v-model="dialogVisible"
      :title="dialogTitle"
      :is-mobile="isMobile"
      :user-form="userForm"
      :form-rules="formRules"
      :current-user-id="currentUserId"
      :editing-user-role="editingUserRole"
      :show-client-form="showClientForm"
      :loading="loading"
      @username-blur="handleUsernameBlur"
      @role-change="handleRoleChange"
      @key-double-click="handleKeyDoubleClick"
      @save="handleSaveUser"
    />

    <UserDetailDialog
      v-model="viewDialogVisible"
      :viewing-user="viewingUser"
      :is-mobile="isMobile"
      :format-date="formatDate"
    />

    <ClientNotificationConfigDialog
      v-model="notificationConfigDialogVisible"
      :client-id="currentClientIdForNotification"
      :client-name="currentClientNameForNotification"
      @saved="handleNotificationConfigSaved"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../../store';
import { useDevice } from '../../composables/useDevice';
import { useUserForm } from '../../composables/useUserForm';
import { useUserRowActions } from '../../composables/useUserRowActions';
import { useUserManagementInit } from '../../composables/useUserManagementInit';
import ClientNotificationConfigDialog from '../../components/admin/ClientNotificationConfigDialog.vue';
import UserColumnSettingDialog from '../../components/admin/UserColumnSettingDialog.vue';
import UserDetailDialog from '../../components/admin/UserDetailDialog.vue';
import UserFilterBar from '../../components/admin/UserFilterBar.vue';
import UserFormDialog from '../../components/admin/UserFormDialog.vue';
import UserPageHeader from '../../components/admin/UserPageHeader.vue';
import UserTable from '../../components/admin/UserTable.vue';
import { useUserColumnVisibility } from '../../composables/useUserColumnVisibility';
import { useUserList } from '../../composables/useUserList';

const authStore = useAuthStore();
const router = useRouter();
const currentUser = computed(() => authStore.userInfo);

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility,
} = useUserColumnVisibility();

const isInitializing = ref(true);
const {
  users,
  loading,
  stats,
  pagination,
  searchForm,
  fetchUsers,
  fetchStats,
  resetFilter,
  bindPaginationWatch,
} = useUserList(authStore, router);

bindPaginationWatch(isInitializing);

useUserManagementInit({
  loadColumnVisibility,
  fetchUsers,
  fetchStats,
  loading,
  isInitializing,
});

const { isMobile } = useDevice();

const {
  dialogVisible,
  viewDialogVisible,
  dialogTitle,
  currentUserId,
  viewingUser,
  userForm,
  showClientForm,
  formRules,
  formatDate,
  handleUsernameBlur,
  handleRoleChange,
  handleAddUser,
  handleView,
  handleKeyDoubleClick,
  handleEdit,
  handleSaveUser,
} = useUserForm({ users, loading, fetchUsers, fetchStats });

const editingUserRole = computed(() => {
  if (!currentUserId.value) return null;
  return users.value.find((u) => u.id === currentUserId.value)?.role ?? null;
});

const {
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
} = useUserRowActions({ fetchUsers, fetchStats });

const hasClientUsers = computed(() => users.value.some((user) => user.role === 'client'));

const handleSortChange = () => {
  // 排序功能可在后续版本中实现
};
</script>

<style scoped src="../../styles/user-management.css"></style>
