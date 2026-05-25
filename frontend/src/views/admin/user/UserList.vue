<!--
用户列表组件
从 UserManagement.vue 拆分
-->
<template>
  <div class="user-list-container">
    <!-- 筛选 -->
    <el-card class="filter-card">
      <el-form :model="filterForm" :inline="true" size="default">
        <el-form-item label="搜索">
          <el-input
            v-model="filterForm.search"
            placeholder="搜索用户名"
            clearable
            @clear="handleSearch"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
        </el-form-item>

        <el-form-item label="角色">
          <el-select v-model="filterForm.role" placeholder="全部" clearable class="w-150">
            <el-option label="管理员" value="admin" />
            <el-option label="客户" value="client" />
          </el-select>
        </el-form-item>

        <el-form-item label="状态">
          <el-select v-model="filterForm.is_active" placeholder="全部" clearable class="w-150">
            <el-option label="激活" :value="true" />
            <el-option label="禁用" :value="false" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleSearch">
            <el-icon><Search /></el-icon>搜索
          </el-button>
          <el-button @click="handleReset">
            <el-icon><Refresh /></el-icon>重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 表格 -->
    <el-card class="table-card">
      <div class="table-header">
        <el-button type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>新建用户
        </el-button>
      </div>

      <el-table v-loading="loading" :data="users" border stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" min-width="150" />
        <el-table-column prop="full_name" label="全名" min-width="120" />
        <el-table-column prop="email" label="邮箱" min-width="180" />
        <el-table-column prop="role" label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'primary'">
              {{ row.role === 'admin' ? '管理员' : '客户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '激活' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Search, Refresh, Plus } from '@element-plus/icons-vue';
import { getUsers, deleteUser } from '@/api/user';

const filterForm = reactive({ search: '', role: '', is_active: null });
const pagination = reactive({ page: 1, page_size: 20, total: 0 });
const users = ref([]);
const loading = ref(false);

const loadUsers = async () => {
  loading.value = true;
  try {
    const response = await getUsers({ ...filterForm, page: pagination.page, page_size: pagination.page_size });
    users.value = response.data || [];
    pagination.total = response.total || 0;
  } catch (error) {
    ElMessage.error('加载用户列表失败');
  } finally {
    loading.value = false;
  }
};

const handleSearch = () => { pagination.page = 1; loadUsers(); };
const handleReset = () => {
  Object.assign(filterForm, { search: '', role: '', is_active: null });
  pagination.page = 1;
  loadUsers();
};
const handlePageChange = (page) => { pagination.page = page; loadUsers(); };
const handleSizeChange = (size) => { pagination.page_size = size; pagination.page = 1; loadUsers(); };
const handleCreate = () => { ElMessage.info('打开创建对话框'); };
const handleEdit = (row) => { ElMessage.info(`编辑用户：${row.username}`); };
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除用户 "${row.username}"？`, '警告', { type: 'warning' });
    await deleteUser(row.id);
    ElMessage.success('删除成功');
    loadUsers();
  } catch (error) { if (error !== 'cancel') ElMessage.error('删除失败'); }
};

onMounted(() => { loadUsers(); });
defineExpose({ refresh: loadUsers });
</script>

<style scoped>
.user-list-container { padding: 20px; }
.filter-card { margin-bottom: 20px; }
.w-150 { width: 150px; }
.table-header { display: flex; justify-content: space-between; margin-bottom: 16px; }
.pagination-container { margin-top: 20px; display: flex; justify-content: flex-end; }
</style>
