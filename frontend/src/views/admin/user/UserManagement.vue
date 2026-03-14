<!--
用户管理主页面（重构版）
协调子组件：列表、表单
-->
<template>
  <div class="user-management">
    <div class="page-header">
      <h2>用户管理</h2>
      <el-button type="primary" @click="handleCreate"><el-icon><Plus /></el-icon>新建用户</el-button>
    </div>
    <UserList ref="listRef" @create="handleCreate" @edit="handleEdit" @delete="handleDelete" />
    <UserForm v-model="formVisible" :user-id="selectedUserId" @success="handleFormSuccess" />
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { Plus } from '@element-plus/icons-vue';
import UserList from './UserList.vue';
import UserForm from './UserForm.vue';

const listRef = ref(null);
const formVisible = ref(false);
const selectedUserId = ref(null);

const handleCreate = () => { selectedUserId.value = null; formVisible.value = true; };
const handleEdit = (row) => { selectedUserId.value = row.id; formVisible.value = true; };
const handleDelete = async (row) => { console.log('删除用户:', row.id); };
const handleFormSuccess = () => { if (listRef.value) listRef.value.refresh(); selectedUserId.value = null; };
</script>

<style scoped>
.user-management { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 24px; color: #303133; }
</style>
