<!--
  用户管理筛选栏
  @file components/admin/UserFilterBar.vue
-->
<template>
  <el-card class="filter-card" shadow="never">
    <el-form :inline="true" :model="searchForm" class="filter-form">
      <el-form-item label="用户名">
        <el-input
          v-model="searchForm.username"
          placeholder="输入用户名搜索"
          clearable
          style="width: 200px;"
          :prefix-icon="Search"
          name="username"
          @keyup.enter="emit('search')"
        />
      </el-form-item>
      <el-form-item label="角色">
        <el-select v-model="searchForm.role" placeholder="全部角色" clearable style="width: 180px;" name="role">
          <el-option label="全部角色" value="" />
          <el-option label="管理员" value="admin" />
          <el-option label="客户" value="client" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="searchForm.status" placeholder="全部状态" clearable style="width: 180px;" name="status">
          <el-option label="全部状态" value="" />
          <el-option label="启用" value="active" />
          <el-option label="禁用" value="inactive" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" :icon="Search" @click="emit('search')">
          查询
        </el-button>
        <el-button :icon="Refresh" @click="emit('reset')">
          重置
        </el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { ElButton, ElCard, ElForm, ElFormItem, ElInput, ElOption, ElSelect } from 'element-plus';
import { Refresh, Search } from '@element-plus/icons-vue';

defineProps({
  searchForm: { type: Object, required: true },
  loading: { type: Boolean, default: false },
});

const emit = defineEmits(['search', 'reset']);
</script>

<style scoped src="../../styles/user-management.css"></style>
