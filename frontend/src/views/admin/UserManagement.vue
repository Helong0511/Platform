<template>
  <div class="user-management-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1>用户管理</h1>
        <div class="stats-info" v-if="stats">
          <span class="stat-item">
            <span class="stat-label">总用户数：</span>
            <span class="stat-value">{{ stats.total_users }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">管理员：</span>
            <span class="stat-value">{{ stats.by_role?.admin || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">客户：</span>
            <span class="stat-value">{{ stats.by_role?.client || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">启用：</span>
            <span class="stat-value success">{{ stats.by_status?.active || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">禁用：</span>
            <span class="stat-value danger">{{ stats.by_status?.inactive || 0 }}</span>
          </span>
        </div>
      </div>
      <div class="action-buttons">
        <el-button type="primary" @click="handleAddUser" :icon="Plus">
          添加用户
        </el-button>
      </div>
    </div>

    <!-- 筛选控件 -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="用户名">
          <el-input 
            v-model="searchForm.username" 
            placeholder="输入用户名搜索" 
            clearable
            @keyup.enter="fetchUsers"
            style="width: 200px;"
            :prefix-icon="Search"
            name="username"
          >
          </el-input>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="searchForm.role" placeholder="全部角色" clearable style="width: 180px;" name="role">
            <el-option label="全部角色" value=""></el-option>
            <el-option label="管理员" value="admin"></el-option>
            <el-option label="客户" value="client"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部状态" clearable style="width: 180px;" name="status">
            <el-option label="全部状态" value=""></el-option>
            <el-option label="启用" value="active"></el-option>
            <el-option label="禁用" value="inactive"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchUsers" :loading="loading" :icon="Search">
            查询
          </el-button>
          <el-button @click="resetFilter" :icon="Refresh">
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 用户数据表格 -->
    <el-card class="data-table-card" shadow="never">
      <template #header>
        <div class="table-header">
          <span>用户列表</span>
          <el-button 
            type="text" 
            :icon="Setting" 
            @click="columnSettingVisible = true"
            style="float: right;"
          >
            列设置
          </el-button>
        </div>
      </template>
      <el-table
        v-loading="loading"
        :data="users"
        border
        stripe
        style="width: 100%"
        @sort-change="handleSortChange"
      >
        <el-table-column v-if="columnVisibility.id" prop="id" label="ID" width="80" sortable="custom" align="center"></el-table-column>
        <el-table-column v-if="columnVisibility.username" prop="username" label="登录用户名" sortable="custom" min-width="80" show-overflow-tooltip>
          <template #default="scope">
            <div class="username-cell">
              <span class="username-text">{{ scope.row.username || '-' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.full_name" prop="full_name" label="全名" min-width="100" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.full_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.role" prop="role" label="角色" width="100" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.role === 'admin' ? 'primary' : 'success'" size="small">
              {{ scope.row.role === 'admin' ? '管理员' : '客户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.email" prop="email" label="邮箱" min-width="200" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.email || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.is_active" prop="is_active" label="状态" width="100" align="center">
          <template #default="scope">
            <el-switch
              v-model="scope.row.is_active"
              @change="handleStatusChange(scope.row)"
              :active-text="scope.row.is_active ? '启用' : ''"
              :inactive-text="!scope.row.is_active ? '禁用' : ''"
              aria-label="切换状态"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="hasClientUsers && columnVisibility.api_enabled" prop="api_enabled" label="API访问" width="120" align="center">
          <template #default="scope">
            <el-switch
              v-if="scope.row.role === 'client'"
              v-model="scope.row.api_enabled"
              @change="(val) => handleApiSwitchChange(scope.row, val)"
              :loading="scope.row._apiSwitchLoading"
              :disabled="scope.row._apiSwitchLoading || loading"
              :active-text="scope.row.api_enabled ? '启用' : ''"
              :inactive-text="!scope.row.api_enabled ? '禁用' : ''"
              aria-label="切换API访问权限"
            ></el-switch>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="hasClientUsers && columnVisibility.password_change_enabled" prop="password_change_enabled" label="允许修改密码" width="140" align="center">
          <template #default="scope">
            <el-switch
              v-if="scope.row.role === 'client'"
              v-model="scope.row.password_change_enabled"
              @change="(val) => handlePasswordSwitchChange(scope.row, val)"
              :loading="scope.row._passwordSwitchLoading"
              :disabled="scope.row._passwordSwitchLoading || loading"
              :active-text="scope.row.password_change_enabled ? '允许' : ''"
              :inactive-text="!scope.row.password_change_enabled ? '禁止' : ''"
              aria-label="切换密码修改权限"
            ></el-switch>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.created_at" prop="created_at" label="创建时间" width="180" sortable="custom">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="350" fixed="right">
          <template #default="scope">
            <div class="operation-buttons">
              <el-button 
                size="small" 
                type="info" 
                :icon="View"
                @click="handleView(scope.row)"
                title="查看详情"
              >
                查看
              </el-button>
              <el-button 
                size="small" 
                type="primary" 
                :icon="Edit"
                @click="handleEdit(scope.row)"
                title="编辑用户"
              >
                编辑
              </el-button>
              <el-button 
                v-if="scope.row.role === 'client'"
                size="small" 
                type="success" 
                :icon="Box"
                @click="handleManageProducts(scope.row)"
                title="管理产品"
                class="product-button"
              >
                产品
              </el-button>
              <el-button 
                v-if="scope.row.role === 'client'"
                size="small" 
                type="warning" 
                :icon="Bell"
                @click="handleNotificationConfig(scope.row)"
                title="通知配置"
              >
                通知
              </el-button>
              <el-button 
                size="small" 
                :type="scope.row.is_active ? 'warning' : 'success'" 
                :icon="scope.row.is_active ? Lock : Unlock"
                @click="handleStatusChange(scope.row)"
                :title="scope.row.is_active ? '禁用用户' : '启用用户'"
              >
                {{ scope.row.is_active ? '禁用' : '启用' }}
              </el-button>
              <el-button 
                size="small" 
                type="danger" 
                :icon="Delete"
                @click="handleDelete(scope.row.id)"
                :disabled="scope.row.id === currentUser?.id"
                :title="scope.row.id === currentUser?.id ? '不能删除自己的账户' : '删除用户'"
              >
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页控件 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.size"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          :layout="isMobile ? 'total, prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
        ></el-pagination>
      </div>
    </el-card>

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="id" :disabled="true">ID（固定显示）</el-checkbox>
        <el-checkbox label="username" :disabled="true">登录用户名（固定显示）</el-checkbox>
        <el-checkbox label="full_name">全名</el-checkbox>
        <el-checkbox label="role">角色</el-checkbox>
        <el-checkbox label="email">邮箱</el-checkbox>
        <el-checkbox label="is_active">状态</el-checkbox>
        <el-checkbox v-if="hasClientUsers" label="api_enabled">API访问</el-checkbox>
        <el-checkbox v-if="hasClientUsers" label="password_change_enabled">允许修改密码</el-checkbox>
        <el-checkbox label="created_at">创建时间</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>

    <!-- 添加/编辑用户模态框 -->
    <el-dialog 
      v-model="dialogVisible" 
      :title="dialogTitle" 
      :width="isMobile ? '95%' : '800px'"
      :close-on-click-modal="false"
      :append-to-body="true"
      destroy-on-close
    >
      <el-form 
        ref="userFormRef" 
        :model="userForm" 
        :rules="formRules" 
        :label-width="isMobile ? '0' : '120px'"
        @submit.prevent
      >
        <el-divider content-position="left">用户信息</el-divider>
        <el-row :gutter="20">
          <el-col :xs="24" :sm="24" :md="12" :lg="12">
            <el-form-item label="登录名" prop="username">
              <el-input 
                v-model="userForm.username" 
                name="username"
                placeholder="请输入登录名（用户名）" 
                clearable
                :disabled="!!currentUserId && (users.find(u => u.id === currentUserId)?.role === 'admin')"
                @blur="handleUsernameBlur"
              ></el-input>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="24" :md="12" :lg="12">
            <el-form-item label="全名" prop="full_name">
              <el-input v-model="userForm.full_name" name="full_name" placeholder="请输入全名" clearable></el-input>
            </el-form-item>
            <div class="form-hint" style="margin-top: 4px; margin-left: 120px;">
              <el-icon :size="16"><InfoFilled /></el-icon>
              <span>全局使用</span>
            </div>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :xs="24" :sm="24" :md="12" :lg="12">
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="userForm.email" name="email" type="email" placeholder="请输入邮箱" clearable></el-input>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="24" :md="12" :lg="12">
            <el-form-item label="角色" prop="role">
              <el-select
                v-model="userForm.role"
                name="role"
                placeholder="请选择角色"
                style="width: 100%;"
                popper-class="select-dropdown"
                :teleported="true"
                @change="handleRoleChange"
                :disabled="!!currentUserId && (users.find(u => u.id === currentUserId)?.role === 'admin')"
              >
                <el-option label="管理员" value="admin"></el-option>
                <el-option label="客户" value="client"></el-option>
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :xs="24" :sm="24" :md="12" :lg="12">
            <el-form-item label="密码" :prop="!currentUserId ? 'password' : undefined">
              <el-input 
                v-model="userForm.password" 
                name="password"
                type="password" 
                :placeholder="!currentUserId ? '请输入密码（至少6位，最多72字符）' : '留空则不修改密码'"
                show-password 
                clearable
                maxlength="72"
              ></el-input>
              <div class="form-hint" style="margin-top: 4px; margin-left: 120px;" v-if="!currentUserId">
                <el-icon :size="16"><InfoFilled /></el-icon>
                <span>密码长度限制：6-72个字符（bcrypt算法限制）</span>
              </div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="24" :md="12" :lg="12">
            <el-form-item label="状态">
              <el-switch
                v-model="userForm.is_active"
                active-text="启用"
                inactive-text="禁用"
                aria-label="切换用户状态"
              ></el-switch>
            </el-form-item>
          </el-col>
        </el-row>
        
        <template v-if="showClientForm">
          <el-divider content-position="left">客户信息</el-divider>
          <el-row :gutter="20">
            <el-col :span="24">
              <el-form-item label="API密钥">
                <div class="key-input-with-button">
                  <div @dblclick="handleKeyDoubleClick" class="key-input-wrapper">
                    <el-input 
                      v-model="userForm.client_key" 
                      name="client_key"
                      placeholder="客户API密钥UUID（创建时自动生成）"
                      :disabled="!userForm.isKeyEditable && !currentUserId"
                      class="key-input-field"
                      readonly
                      style="font-family: monospace; font-size: 13px;"
                      :prefix-icon="Key"
                    >
                    </el-input>
                  </div>
                  <el-button 
                    v-if="currentUserId"
                    type="primary" 
                    :icon="Refresh" 
                    @click="handleKeyDoubleClick"
                    class="generate-key-button"
                  >
                    生成新密钥
                  </el-button>
                </div>
                <div style="font-size: 12px; color: #909399; margin-top: 4px;">
                  <span v-if="!currentUserId">客户API密钥将在创建时由系统自动生成</span>
                  <span v-else-if="!userForm.isKeyEditable">客户API密钥，由系统自动生成，双击输入框或点击"生成新密钥"按钮自动生成新UUID</span>
                  <span v-else style="color: #e6a23c;">⚠️ 已自动生成新UUID，您可以继续编辑或直接保存</span>
                </div>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :xs="24" :sm="24" :md="12" :lg="12">
              <el-form-item label="公司名称" prop="company_name">
                <el-input v-model="userForm.company_name" name="company_name" placeholder="请输入公司名称" clearable></el-input>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="24" :md="12" :lg="12">
              <el-form-item label="联系人" prop="contact_person">
                <el-input v-model="userForm.contact_person" name="contact_person" placeholder="请输入联系人姓名" clearable></el-input>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :xs="24" :sm="24" :md="12" :lg="12">
              <el-form-item label="联系电话" prop="phone">
                <el-input v-model="userForm.phone" name="phone" placeholder="请输入联系电话" clearable></el-input>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="24" :md="24" :lg="24">
              <el-form-item label="地址" prop="address">
                <el-input 
                  v-model="userForm.address" 
                  name="address"
                  type="textarea" 
                  :rows="3" 
                  placeholder="请输入公司地址" 
                  clearable
                ></el-input>
              </el-form-item>
            </el-col>
          </el-row>
        </template>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSaveUser" :loading="loading">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 用户详情查看对话框 -->
    <el-dialog 
      v-model="viewDialogVisible" 
      :title="viewingUser?.role === 'admin' ? '管理员详情' : '客户详情'" 
      :width="isMobile ? '95%' : '700px'"
    >
      <div v-if="viewingUser" class="user-detail">
        <el-descriptions :column="isMobile ? 1 : 2" border>
          <el-descriptions-item label="用户ID">{{ viewingUser.id }}</el-descriptions-item>
          <el-descriptions-item label="登录用户名">{{ viewingUser.username }}</el-descriptions-item>
          <el-descriptions-item label="邮箱">{{ viewingUser.email || '-' }}</el-descriptions-item>
          <el-descriptions-item label="全名">{{ viewingUser.full_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="角色">
            <el-tag :type="viewingUser.role === 'admin' ? 'primary' : 'success'">
              {{ viewingUser.role === 'admin' ? '管理员' : '客户' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="viewingUser.is_active ? 'success' : 'danger'">
              {{ viewingUser.is_active ? '启用' : '禁用' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间" :span="2">
            {{ formatDate(viewingUser.created_at) }}
          </el-descriptions-item>
          
          <!-- 管理员特有信息 -->
          <template v-if="viewingUser.role === 'admin'">
            <el-descriptions-item label="最后更新" :span="2">
              {{ formatDate(viewingUser.updated_at) }}
            </el-descriptions-item>
          </template>
          
          <!-- 客户特有信息 -->
          <template v-if="viewingUser.role === 'client'">
            <el-divider content-position="left">客户信息</el-divider>
            <template v-if="viewingUser.client">
              <el-descriptions-item label="客户ID">{{ viewingUser.client.id }}</el-descriptions-item>
              <el-descriptions-item label="API密钥" :span="2">
                <span v-if="viewingUser.client.key" style="font-family: monospace; font-size: 12px;">{{ viewingUser.client.key }}</span>
                <span v-else style="color: #909399;">-</span>
              </el-descriptions-item>
              <el-descriptions-item label="客户状态">
                <el-tag :type="viewingUser.client.is_active ? 'success' : 'danger'" size="small">
                  {{ viewingUser.client.is_active ? '启用' : '禁用' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="公司名称" :span="2">{{ viewingUser.client.company_name || '-' }}</el-descriptions-item>
              <el-descriptions-item label="联系人">{{ viewingUser.client.contact_person || '-' }}</el-descriptions-item>
              <el-descriptions-item label="联系电话">{{ viewingUser.client.phone || '-' }}</el-descriptions-item>
              <el-descriptions-item label="公司地址" :span="2">{{ viewingUser.client.address || '-' }}</el-descriptions-item>
            </template>
            <template v-else>
              <el-descriptions-item label="客户信息" :span="2">
                <el-tag type="warning" size="small">暂无客户信息</el-tag>
              </el-descriptions-item>
            </template>
          </template>
        </el-descriptions>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="viewDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 产品管理对话框 -->
    <ProductManagementDialog
      v-model="productDialogVisible"
      :client-name="currentClientName"
      :client-id="currentClientIdForProducts"
      :products="products"
      :loading="productLoading"
      @save="saveProduct"
      @delete="removeProduct"
      @refresh="handleProductRefresh"
    />

    <!-- 客户通知配置对话框 -->
    <ClientNotificationConfigDialog
      v-model="notificationConfigDialogVisible"
      :client-id="currentClientIdForNotification"
      :client-name="currentClientNameForNotification"
      @saved="handleNotificationConfigSaved"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, computed, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { 
  ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem, 
  ElInput, ElSelect, ElOption, ElTag, ElDialog, ElIcon, ElMessage, ElMessageBox, 
  ElDivider, ElSwitch, ElDescriptions, ElDescriptionsItem, ElRow, ElCol, ElCheckboxGroup, ElCheckbox
} from 'element-plus';
import { 
  Plus, Search, Refresh, Lock, Unlock, Delete, View, Edit, Box, InfoFilled, Key, Setting
} from '@element-plus/icons-vue';
import { useAuthStore } from '../../store';
import { useDevice } from '../../composables/useDevice';
import { useClientProducts } from '../../composables/useClientProducts';
import { useUserForm } from '../../composables/useUserForm';
import { useUserRowActions } from '../../composables/useUserRowActions';
import ProductManagementDialog from '../../components/admin/ProductManagementDialog.vue';
import ClientNotificationConfigDialog from '../../components/admin/ClientNotificationConfigDialog.vue';
import { useUserColumnVisibility } from '../../composables/useUserColumnVisibility';
import { useUserList } from '../../composables/useUserList';
import { extractErrorMessage, isErrorHandled } from '../../utils/api';

// Store
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

const { isMobile } = useDevice();

const {
  productDialogVisible,
  currentClientIdForProducts,
  currentClientName,
  products,
  productLoading,
  openProductDialog,
  fetchProductsForClient,
  saveProduct,
  removeProduct,
} = useClientProducts();

const {
  dialogVisible,
  viewDialogVisible,
  dialogTitle,
  currentUserId,
  viewingUser,
  userFormRef,
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
} = useUserRowActions({ fetchUsers, fetchStats, openProductDialog });

const showClientInfo = computed(() => users.value.some((user) => user.client));

const hasClientUsers = computed(() => users.value.some((user) => user.role === 'client'));

const handleProductRefresh = async () => {
  await fetchProductsForClient(currentClientIdForProducts.value);
  await fetchUsers();
};

const handleSortChange = () => {
  // 排序功能可在后续版本中实现
};

// 初始化
onMounted(async () => {
  // 加载列显示设置
  loadColumnVisibility();
  // 路由守卫已经处理了认证检查，这里不需要重复检查
  // 延迟加载数据，让页面先渲染出来
  await nextTick();
  
  setTimeout(async () => {
    try {
      // 设置超时保护（20秒）
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => {
          reject(new Error('页面加载超时，请检查网络连接或刷新页面'));
        }, 20000);
      });
      
      // 优化请求顺序：先获取用户列表，再获取统计信息，避免同时发送导致限流
      await Promise.race([
        (async () => {
          // 先获取用户列表
          await fetchUsers(true);
          // 延迟 200ms 后再获取统计信息，避免同时发送
          await new Promise(resolve => setTimeout(resolve, 200));
          await fetchStats();
        })(),
        timeoutPromise
      ]);
    } catch (error) {
      // 超时或其他错误
      if (error.message && error.message.includes('超时')) {
        ElMessage.error(error.message);
        loading.value = false;
      } else if (error.response?.status === 401) {
        // 401错误已在拦截器中处理
        loading.value = false;
      } else {
        // 初始化失败时的错误处理
        if (!isErrorHandled(error)) {
          const errorMsg = extractErrorMessage(error);
          ElMessage.error(`页面初始化失败: ${errorMsg}`);
        }
        loading.value = false;
      }
    } finally {
      // 初始化完成后，允许 watch 触发
      await nextTick();
      isInitializing.value = false;
    }
  }, 0);
});
</script>

<style scoped>
.user-management-container {
  width: 100%;
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-xl);
  padding: var(--spacing-xl);
  background-color: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
  flex-wrap: wrap;
  gap: var(--spacing-md);
}

.header-left {
  flex: 1;
  min-width: 300px;
}

.page-header h1 {
  margin: 0 0 var(--spacing-md) 0;
  font-size: var(--font-size-title);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.stats-info {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-lg);
  padding: var(--spacing-sm) 0;
}

.stat-item {
  display: flex;
  align-items: center;
  font-size: var(--font-size-base);
}

.stat-label {
  color: var(--text-secondary);
  margin-right: var(--spacing-xs);
}

.stat-value {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.stat-value.success {
  color: var(--success-color);
}

.stat-value.danger {
  color: var(--danger-color);
}

.action-buttons {
  display: flex;
  gap: var(--spacing-md);
  flex-wrap: wrap;
}

.filter-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.filter-form {
  margin: 0;
}

.data-table-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
  overflow: hidden;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.data-table-card :deep(.el-card__body) {
  padding: var(--spacing-xl);
}

.selected-count {
  color: var(--primary-color);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
}

.username-cell {
  display: flex;
  align-items: center;
}

.operation-buttons {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.operation-buttons .el-button {
  margin: 0;
  padding: 7px 12px;
  font-size: 12px;
  min-width: auto;
  white-space: nowrap;
}

.operation-buttons .el-button + .el-button {
  margin-left: 0;
}

.operation-buttons .product-button {
  min-width: 70px;
  padding: 7px 14px;
}

.username-text {
  font-weight: 500;
}

.client-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.company-name {
  font-weight: 500;
  color: #303133;
}

.company-phone {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
}

.empty-text {
  color: #c0c4cc;
}

.pagination-container {
  margin-top: var(--spacing-lg);
  padding: var(--spacing-lg) 0;
  text-align: right;
  border-top: 1px solid var(--border-lighter);
}

.user-detail {
  padding: 10px 0;
}

/* 全名字段包装器 */
.full-name-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs, 8px);
  width: 100%;
}

.form-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs, 8px);
  font-size: var(--font-size-sm, 14px);
  color: var(--text-secondary, #909399);
  margin-top: 0;
  padding: var(--spacing-xs, 8px) var(--spacing-sm, 12px);
  background-color: #f5f7fa;
  border-radius: var(--radius-md, 4px);
}

.form-hint .el-icon {
  color: var(--primary-color, #409eff);
  font-size: var(--font-size-base, 16px);
}

/* 移动端优化 */
@media (max-width: 767px) {
  .user-management-container {
    padding: var(--spacing-md);
  }
  
  .page-header {
    flex-direction: column;
    margin-bottom: var(--spacing-md);
  }
  
  .header-left {
    min-width: 100%;
  }
  
  .page-header h1 {
    font-size: var(--font-size-xl);
    margin-bottom: var(--spacing-sm);
  }
  
  .stats-info {
    flex-direction: column;
    gap: var(--spacing-sm);
    padding: var(--spacing-sm) 0;
  }
  
  .stat-item {
    font-size: var(--font-size-sm);
  }
  
  .action-buttons {
    width: 100%;
  }
  
  .action-buttons .el-button {
    width: 100%;
    min-height: var(--touch-target-size);
  }
  
  .filter-card {
    margin-bottom: var(--spacing-md);
  }
  
  /* 筛选表单移动端优化 - 强制覆盖 inline 表单样式 */
  .filter-form {
    display: flex !important;
    flex-direction: column !important;
  }
  
  .filter-form :deep(.el-form--inline) {
    display: flex !important;
    flex-direction: column !important;
  }
  
  .filter-form :deep(.el-form-item) {
    width: 100% !important;
    margin-right: 0 !important;
    margin-bottom: var(--spacing-md) !important;
    display: flex !important;
    flex-direction: column !important;
  }
  
  .filter-form :deep(.el-form-item__label) {
    width: 100% !important;
    text-align: left !important;
    margin-bottom: var(--spacing-xs) !important;
    padding: 0 !important;
    margin-right: 0 !important;
    float: none !important;
    justify-content: flex-start !important;
    align-items: flex-start !important;
    display: block !important;
  }
  
  .filter-form :deep(.el-form-item__content) {
    width: 100% !important;
    margin-left: 0 !important;
    flex: 1 !important;
  }
  
  .filter-form :deep(.el-input),
  .filter-form :deep(.el-select) {
    width: 100% !important;
    max-width: 100% !important;
  }
  
  .filter-form :deep(.el-input__wrapper) {
    min-height: var(--touch-target-size);
    width: 100% !important;
  }
  
  .filter-form :deep(.el-select .el-input__wrapper) {
    min-height: var(--touch-target-size);
    width: 100% !important;
  }
  
  /* 查询和重置按钮移动端优化 */
  .filter-form :deep(.el-form-item:last-child) {
    display: flex !important;
    flex-direction: row !important;
    gap: var(--spacing-sm);
    margin-top: var(--spacing-sm);
    margin-bottom: 0 !important;
    width: 100% !important;
  }
  
  .filter-form :deep(.el-form-item:last-child .el-form-item__label) {
    display: none !important; /* Hide label for buttons */
  }
  
  .filter-form :deep(.el-form-item:last-child .el-form-item__content) {
    width: 100% !important;
    display: flex !important;
    flex-direction: row !important;
    gap: var(--spacing-sm);
  }
  
  .filter-form :deep(.el-form-item:last-child .el-button) {
    flex: 1;
    min-height: var(--touch-target-size);
    width: auto;
    white-space: nowrap;
  }
  
  .data-table-card {
    margin-bottom: var(--spacing-md);
  }
  
  .table-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }
  
  .operation-buttons {
    flex-direction: row;
    flex-wrap: wrap;
    gap: var(--spacing-xs);
    width: 100%;
    align-items: center;
    justify-content: flex-start;
  }
  
  .operation-buttons .el-button {
    flex: 0 0 auto;
    min-height: 36px;
    padding: 6px 10px;
    margin: 0;
    font-size: 12px;
    white-space: nowrap;
    line-height: 1.2;
  }
  
  .operation-buttons .el-button .el-icon {
    margin-right: 4px;
    font-size: 14px;
  }
  
  /* 移动端按钮文字缩小显示 */
  .operation-buttons .el-button span {
    font-size: 12px;
  }
  
  .pagination-container {
    margin-top: var(--spacing-md);
    justify-content: center;
  }
  
  /* 移动端对话框优化 */
  .el-dialog {
    width: 95% !important;
    max-width: 95% !important;
    margin: var(--spacing-md) auto !important;
  }
  
  .el-dialog :deep(.el-dialog__header) {
    padding: var(--spacing-md) var(--spacing-lg);
  }
  
  .el-dialog :deep(.el-dialog__title) {
    font-size: var(--font-size-lg);
  }
  
  .el-dialog :deep(.el-dialog__body) {
    padding: var(--spacing-md);
    max-height: calc(100vh - 200px);
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  /* 对话框footer样式 - 覆盖全局样式 */
  .el-dialog :deep(.el-dialog__footer) {
    padding: var(--spacing-md) var(--spacing-lg) !important;
    display: flex !important;
    flex-direction: row !important;
    gap: var(--spacing-sm) !important;
    justify-content: center !important;
    align-items: center !important;
    text-align: center !important;
  }
  
  /* 对话框footer中的按钮容器 - 横向排列并居中 */
  .el-dialog :deep(.el-dialog__footer .dialog-footer) {
    display: flex !important;
    flex-direction: row !important;
    justify-content: center !important;
    align-items: center !important;
    gap: 12px !important;
    width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
  }
  
  /* 对话框footer中的按钮样式 - 缩小尺寸并横向排列 */
  .el-dialog :deep(.el-dialog__footer .el-button),
  .el-dialog :deep(.el-dialog__footer .dialog-footer .el-button) {
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: 90px !important;
    margin: 0 !important;
    padding: 8px 20px !important;
    font-size: var(--font-size-base) !important;
  }
  
  /* 表单布局优化 */
  .el-form :deep(.el-row) {
    margin: 0 !important;
    flex-direction: column !important;
  }
  
  .el-form :deep(.el-col) {
    width: 100% !important;
    padding: 0 !important;
    margin-bottom: var(--spacing-md) !important;
    flex: 0 0 100% !important;
    max-width: 100% !important;
  }
  
  .el-form :deep(.el-form-item) {
    margin-bottom: var(--spacing-md);
  }
  
  .el-form :deep(.el-form-item__label) {
    width: 100% !important;
    text-align: left !important;
    margin-bottom: var(--spacing-xs) !important;
    padding: 0 !important;
    margin-right: 0 !important;
    float: none !important;
    display: block !important;
  }
  
  .el-form :deep(.el-form-item__content) {
    width: 100% !important;
    margin-left: 0 !important;
  }
  
  /* 输入框和选择器优化 */
  .el-form :deep(.el-input),
  .el-form :deep(.el-select),
  .el-form :deep(.el-textarea) {
    width: 100% !important;
  }
  
  .el-form :deep(.el-input__wrapper) {
    min-height: var(--touch-target-size);
  }
  
  .el-form :deep(.el-select .el-input__wrapper) {
    min-height: var(--touch-target-size);
  }
  
  /* 分隔线优化 */
  .el-divider {
    margin: var(--spacing-md) 0 !important;
  }
  
  .el-divider :deep(.el-divider__text) {
    font-size: var(--font-size-base);
    padding: 0 var(--spacing-md);
  }
  
  /* 全名输入框包装器优化 */
  .full-name-wrapper {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
  }
  
  @media (max-width: 767px) {
    .full-name-wrapper {
      gap: var(--spacing-sm);
    }
  }
  
  .form-hint {
    margin-top: var(--spacing-xs);
    font-size: var(--font-size-xs);
    display: flex;
    align-items: center;
    gap: 4px;
    color: #909399;
    word-break: break-word;
    line-height: 1.4;
  }
  
  .form-hint .el-icon {
    font-size: 14px;
    flex-shrink: 0;
  }
  
  /* 移动端优化：全局使用提示 */
  @media (max-width: 767px) {
    .form-hint {
      font-size: var(--font-size-xs);
      margin-top: var(--spacing-sm);
      padding: var(--spacing-xs) var(--spacing-sm);
      background-color: var(--bg-secondary);
      border-radius: var(--radius-sm);
      width: 100%;
    }
  }
  
  /* API密钥输入框优化 */
  .key-input-wrapper {
    min-width: 100% !important;
    width: 100% !important;
  }
  
  .key-input-with-button {
    flex-direction: column;
    gap: var(--spacing-sm);
  }
  
  .key-input-with-button .el-button {
    width: 100%;
    min-height: var(--touch-target-size);
  }
  
  /* API密钥说明文字优化 */
  .key-input-with-button + div {
    font-size: var(--font-size-xs) !important;
    line-height: 1.5 !important;
    word-break: break-word !important;
    margin-top: var(--spacing-sm) !important;
    padding: var(--spacing-xs) var(--spacing-sm) !important;
    background-color: var(--bg-secondary) !important;
    border-radius: var(--radius-sm) !important;
  }
  
  /* 移动端API密钥区域优化 */
  @media (max-width: 767px) {
    .key-input-with-button {
      gap: var(--spacing-md);
    }
    
    .key-input-field {
      font-size: var(--font-size-xs) !important;
    }
    
    .key-input-with-button + div {
      font-size: 11px !important;
      padding: var(--spacing-sm) !important;
    }
  }
  
  /* 开关优化 */
  .el-switch {
    min-width: 44px;
    min-height: var(--touch-target-size);
  }
  
  /* 文本域优化 */
  .el-textarea :deep(.el-textarea__inner) {
    min-height: 80px;
    font-size: var(--font-size-base);
  }
  
  /* 用户详情对话框移动端优化 */
  .user-detail {
    font-size: var(--font-size-sm);
  }
  
  .user-detail :deep(.el-descriptions) {
    font-size: var(--font-size-sm);
  }
  
  .user-detail :deep(.el-descriptions__table) {
    width: 100%;
  }
  
  .user-detail :deep(.el-descriptions__row) {
    display: flex;
    flex-direction: row;
    align-items: flex-start;
  }
  
  .user-detail :deep(.el-descriptions-item) {
    width: 100% !important;
    display: flex;
    flex-direction: row;
    align-items: flex-start;
    padding: var(--spacing-sm) 0;
    border-bottom: 1px solid var(--border-lighter);
    gap: var(--spacing-sm);
  }
  
  .user-detail :deep(.el-descriptions-item:last-child) {
    border-bottom: none;
  }
  
  .user-detail :deep(.el-descriptions__label) {
    width: auto !important;
    min-width: 70px !important;
    max-width: 90px !important;
    flex-shrink: 0 !important;
    text-align: left !important;
    font-weight: var(--font-weight-medium) !important;
    font-size: var(--font-size-xs) !important;
    color: var(--text-secondary) !important;
    margin-bottom: 0 !important;
    margin-right: var(--spacing-sm) !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    line-height: 1.5 !important;
  }
  
  .user-detail :deep(.el-descriptions__content) {
    width: auto !important;
    flex: 1 !important;
    min-width: 0 !important;
    text-align: left !important;
    word-break: break-word !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    font-size: var(--font-size-sm) !important;
    line-height: 1.5 !important;
  }
  
  .user-detail :deep(.el-divider) {
    margin: var(--spacing-md) 0 !important;
  }
  
  .user-detail :deep(.el-divider__text) {
    font-size: var(--font-size-base);
    padding: 0 var(--spacing-md);
  }
  
  /* 移动端表格标题优化 - 防止截断 */
  .el-table :deep(.el-table__header th) {
    white-space: nowrap;
    overflow: visible;
    text-overflow: clip;
    padding: var(--spacing-xs) var(--spacing-sm);
    font-size: var(--font-size-xs);
    font-weight: var(--font-weight-semibold);
  }
  
  /* 移动端表格内容优化 */
  .el-table :deep(.el-table__body td) {
    padding: var(--spacing-xs) var(--spacing-sm);
    word-break: break-word;
  }
  
  /* 移动端表格容器优化 */
  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .el-table {
    min-width: 800px; /* 确保表格有最小宽度，可以横向滚动 */
    font-size: var(--font-size-sm);
  }
  
  /* 移动端分页组件优化 */
  .pagination-container {
    margin-top: var(--spacing-md);
    padding: var(--spacing-sm) 0;
  }
  
  .el-pagination {
    flex-wrap: wrap;
    justify-content: center;
    font-size: var(--font-size-sm);
  }
  
  .el-pagination :deep(.el-pagination__total) {
    margin-right: var(--spacing-sm);
    font-size: var(--font-size-sm);
  }
  
  .el-pagination :deep(.el-pagination__sizes) {
    margin: var(--spacing-xs) 0;
  }
  
  .el-pagination :deep(.el-pagination__jump) {
    margin: var(--spacing-xs) 0;
  }
  
  .el-pagination :deep(.btn-prev),
  .el-pagination :deep(.btn-next),
  .el-pagination :deep(.el-pager li) {
    min-width: var(--touch-target-size);
    min-height: var(--touch-target-size);
    font-size: var(--font-size-sm);
  }
}

/* Key字段样式 */
.key-input-with-button {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  width: 100%;
}

.key-input-wrapper {
  flex: 1;
  cursor: pointer;
  min-width: 350px; /* 确保有足够空间显示完整的UUID */
}

.key-input-field {
  cursor: pointer;
  transition: all 0.3s;
  width: 100%;
}

.key-input-field :deep(.el-input__wrapper) {
  overflow: visible;
  width: 100%;
}

.key-input-field :deep(.el-input__inner) {
  font-family: monospace;
  font-size: 13px;
  letter-spacing: 0.5px;
  overflow: visible;
  text-overflow: clip;
  white-space: nowrap;
  width: 100%;
}

.key-input-field :deep(.el-input__wrapper) {
  transition: all 0.3s;
}

.generate-key-button {
  white-space: nowrap;
  flex-shrink: 0;
}

.key-input-field :deep(.el-input.is-disabled .el-input__wrapper) {
  cursor: pointer;
  background-color: #f5f7fa;
}

.key-input-field :deep(.el-input.is-disabled .el-input__wrapper:hover) {
  background-color: #ebedf0;
  box-shadow: 0 0 0 1px #c0c4cc inset;
}

.key-input-field :deep(.el-input:not(.is-disabled) .el-input__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}

.edit-hint-icon {
  color: #909399;
  font-size: 14px;
  cursor: pointer;
  transition: color 0.3s;
}

.edit-hint-icon:hover {
  color: #409eff;
}
</style>