<!--
  用户管理页头（统计 + 添加按钮）
  @file components/admin/UserPageHeader.vue
-->
<template>
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
      <el-button type="primary" :icon="Plus" @click="emit('add')">
        添加用户
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ElButton } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';

defineProps({
  stats: { type: Object, default: null },
});

const emit = defineEmits(['add']);
</script>

<style scoped src="../../styles/user-management.css"></style>
