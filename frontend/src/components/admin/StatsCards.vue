<template>
  <el-row :gutter="20" class="stats-row">
    <el-col :span="6">
      <el-card class="stat-card stat-card-total">
        <div class="stat-content">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">总客户数</div>
        </div>
        <el-icon class="stat-icon"><UserFilled /></el-icon>
      </el-card>
    </el-col>
    <el-col :span="6">
      <el-card class="stat-card stat-card-active">
        <div class="stat-content">
          <div class="stat-value">{{ stats.active }}</div>
          <div class="stat-label">活跃客户</div>
        </div>
        <el-icon class="stat-icon"><CircleCheck /></el-icon>
      </el-card>
    </el-col>
    <el-col :span="6">
      <el-card class="stat-card stat-card-inactive">
        <div class="stat-content">
          <div class="stat-value">{{ stats.inactive }}</div>
          <div class="stat-label">禁用客户</div>
        </div>
        <el-icon class="stat-icon"><CircleClose /></el-icon>
      </el-card>
    </el-col>
    <el-col :span="6">
      <el-card class="stat-card stat-card-products">
        <div class="stat-content">
          <div class="stat-value">{{ stats.products }}</div>
          <div class="stat-label">关联产品</div>
        </div>
        <el-icon class="stat-icon"><Box /></el-icon>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { ElRow, ElCol, ElCard, ElIcon } from 'element-plus';
import { UserFilled, CircleCheck, CircleClose, Box } from '@element-plus/icons-vue';

defineProps({
  stats: {
    type: Object,
    required: true,
    default: () => ({
      total: 0,
      active: 0,
      inactive: 0,
      products: 0
    })
  }
});
</script>

<style scoped>
.stats-row {
  margin-bottom: var(--spacing-xl);
}

.stat-card {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-lg);
  transition: var(--transition-base);
  cursor: pointer;
  border: 1px solid var(--border-lighter);
  box-shadow: var(--shadow-light);
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-medium);
}

.stat-card-total:hover {
  border-color: var(--primary-color);
}

.stat-card-active:hover {
  border-color: var(--success-color);
}

.stat-card-inactive:hover {
  border-color: var(--danger-color);
}

.stat-card-products:hover {
  border-color: var(--warning-color);
}

.stat-content {
  position: relative;
  z-index: 1;
  padding: var(--spacing-xl);
}

.stat-value {
  font-size: var(--font-size-large-title);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-sm);
  transition: var(--transition-base);
  line-height: var(--line-height-tight);
}

.stat-card:hover .stat-value {
  transform: scale(1.05);
  color: var(--primary-color);
}

.stat-label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  font-weight: var(--font-weight-medium);
}

.stat-icon {
  position: absolute;
  right: var(--spacing-xl);
  top: 50%;
  transform: translateY(-50%);
  font-size: var(--font-size-xxxxl);
  opacity: 0.15;
  color: var(--primary-color);
  transition: var(--transition-base);
}

.stat-card:hover .stat-icon {
  opacity: 0.25;
  transform: translateY(-50%) scale(1.1);
}

@media (max-width: 767px) {
  .stats-row {
    margin-bottom: var(--spacing-md);
  }
  
  .stats-row :deep(.el-col) {
    width: 100% !important;
    flex: 0 0 100% !important;
    max-width: 100% !important;
    margin-bottom: var(--spacing-md);
  }
  
  .stat-card {
    margin-bottom: var(--spacing-md);
  }
  
  .stat-value {
    font-size: var(--font-size-xxl);
  }
  
  .stat-label {
    font-size: var(--font-size-sm);
  }
  
  .stat-icon {
    font-size: var(--font-size-xxl);
    right: var(--spacing-md);
  }
  
  .stat-content {
    padding: var(--spacing-md);
  }
}
</style>

