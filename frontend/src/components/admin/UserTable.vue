<!--
  用户管理列表表格与分页
  @file components/admin/UserTable.vue
-->
<template>
  <el-card class="data-table-card" shadow="never">
    <template #header>
      <div class="table-header">
        <span>用户列表</span>
        <el-button type="link" :icon="Setting" style="float: right;" @click="emit('open-column-settings')">
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
      @sort-change="emit('sort-change', $event)"
    >
      <el-table-column v-if="columnVisibility.id" prop="id" label="ID" width="80" sortable="custom" align="center" />
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
      <el-table-column v-if="hasClientUsers && columnVisibility.company_name" prop="company_name" label="公司名称" min-width="150" show-overflow-tooltip>
        <template #default="scope">
          {{ scope.row.role === 'client' ? (scope.row.client?.company_name || '-') : '-' }}
        </template>
      </el-table-column>
      <el-table-column v-if="hasClientUsers && columnVisibility.contact_person" prop="contact_person" label="联系人" min-width="120" show-overflow-tooltip>
        <template #default="scope">
          {{ scope.row.role === 'client' ? (scope.row.client?.contact_person || '-') : '-' }}
        </template>
      </el-table-column>
      <el-table-column v-if="columnVisibility.is_active" prop="is_active" label="状态" width="100" align="center">
        <template #default="scope">
          <el-switch
            v-model="scope.row.is_active"
            :active-text="scope.row.is_active ? '启用' : ''"
            :inactive-text="!scope.row.is_active ? '禁用' : ''"
            aria-label="切换状态"
            @change="emit('status-change', scope.row)"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="hasClientUsers && columnVisibility.api_enabled" prop="api_enabled" label="API访问" width="120" align="center">
        <template #default="scope">
          <el-switch
            v-if="scope.row.role === 'client'"
            v-model="scope.row.api_enabled"
            :loading="scope.row._apiSwitchLoading"
            :disabled="scope.row._apiSwitchLoading || loading"
            :active-text="scope.row.api_enabled ? '启用' : ''"
            :inactive-text="!scope.row.api_enabled ? '禁用' : ''"
            aria-label="切换API访问权限"
            @change="(val) => emit('api-switch-change', scope.row, val)"
          />
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column v-if="hasClientUsers && columnVisibility.password_change_enabled" prop="password_change_enabled" label="允许修改密码" width="140" align="center">
        <template #default="scope">
          <el-switch
            v-if="scope.row.role === 'client'"
            v-model="scope.row.password_change_enabled"
            :loading="scope.row._passwordSwitchLoading"
            :disabled="scope.row._passwordSwitchLoading || loading"
            :active-text="scope.row.password_change_enabled ? '允许' : ''"
            :inactive-text="!scope.row.password_change_enabled ? '禁止' : ''"
            aria-label="切换密码修改权限"
            @change="(val) => emit('password-switch-change', scope.row, val)"
          />
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
            <el-button size="small" type="info" :icon="View" title="查看详情" @click="emit('view', scope.row)">
              查看
            </el-button>
            <el-button size="small" type="primary" :icon="Edit" title="编辑用户" @click="emit('edit', scope.row)">
              编辑
            </el-button>
            <el-button
              v-if="scope.row.role === 'client'"
              size="small"
              type="success"
              :icon="Box"
              title="管理产品"
              class="product-button"
              @click="emit('manage-products', scope.row)"
            >
              产品
            </el-button>
            <el-button
              v-if="scope.row.role === 'client'"
              size="small"
              type="warning"
              :icon="Bell"
              title="通知配置"
              @click="emit('notification-config', scope.row)"
            >
              通知
            </el-button>
            <el-button
              size="small"
              :type="scope.row.is_active ? 'warning' : 'success'"
              :icon="scope.row.is_active ? Lock : Unlock"
              :title="scope.row.is_active ? '禁用用户' : '启用用户'"
              @click="emit('status-change', scope.row)"
            >
              {{ scope.row.is_active ? '禁用' : '启用' }}
            </el-button>
            <el-button
              size="small"
              type="danger"
              :icon="Delete"
              :disabled="scope.row.id === currentUserId"
              :title="scope.row.id === currentUserId ? '不能删除自己的账户' : '删除用户'"
              @click="emit('delete', scope.row.id)"
            >
              删除
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-container">
      <el-pagination
        v-model:current-page="pagination.current"
        v-model:page-size="pagination.size"
        :page-sizes="[10, 20, 50, 100]"
        :total="pagination.total"
        :layout="isMobile ? 'total, prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
      />
    </div>
  </el-card>
</template>

<script setup>
import { ElButton, ElCard, ElPagination, ElSwitch, ElTable, ElTableColumn, ElTag } from 'element-plus';
import { Bell, Box, Delete, Edit, Lock, Setting, Unlock, View } from '@element-plus/icons-vue';

defineProps({
  users: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  columnVisibility: { type: Object, required: true },
  hasClientUsers: { type: Boolean, default: false },
  formatDate: { type: Function, required: true },
  currentUserId: { type: Number, default: null },
  isMobile: { type: Boolean, default: false },
  pagination: { type: Object, required: true },
});

const emit = defineEmits([
  'open-column-settings',
  'sort-change',
  'status-change',
  'api-switch-change',
  'password-switch-change',
  'view',
  'edit',
  'manage-products',
  'notification-config',
  'delete',
]);
</script>

<style scoped src="../../styles/user-management.css"></style>
