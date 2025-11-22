<template>
  <el-table
    v-loading="loading"
    :data="clients"
    border
    stripe
    style="width: 100%"
    :default-sort="{ prop: 'id', order: 'descending' }"
    @selection-change="$emit('selection-change', $event)"
    empty-text="暂无客户数据"
  >
    <el-table-column type="selection" width="55" align="center"></el-table-column>
    <el-table-column prop="id" label="ID" width="80" sortable align="center"></el-table-column>
    <el-table-column prop="key" label="API密钥" width="280" show-overflow-tooltip>
      <template #default="scope">
        <span v-if="scope.row.key" class="key-text">{{ scope.row.key }}</span>
        <span v-else class="text-muted">-</span>
      </template>
    </el-table-column>
    <el-table-column prop="company_name" label="公司名称" min-width="180" sortable show-overflow-tooltip>
      <template #default="scope">
        <div class="company-name-cell">
          <span class="company-name">{{ scope.row.company_name }}</span>
        </div>
      </template>
    </el-table-column>
    <el-table-column prop="user_name" label="关联用户" width="120" show-overflow-tooltip>
      <template #default="scope">
        <el-tag size="small" type="info">
          {{ scope.row.user_name || '未知用户' }}
        </el-tag>
        <div v-if="scope.row.user_name" class="user-relation-info">
          <el-icon :size="12"><User /></el-icon>
          <span class="relation-hint">ID: {{ scope.row.user_id }}</span>
        </div>
      </template>
    </el-table-column>
    <el-table-column prop="contact_person" label="联系人" width="120" show-overflow-tooltip></el-table-column>
    <el-table-column prop="phone" label="联系电话" width="140" show-overflow-tooltip>
      <template #default="scope">
        <span v-if="scope.row.phone" class="phone-link" @click="$emit('copy-phone', scope.row.phone)">
          {{ scope.row.phone }}
        </span>
        <span v-else class="text-muted">-</span>
      </template>
    </el-table-column>
    <el-table-column prop="address" label="地址" min-width="200" show-overflow-tooltip>
      <template #default="scope">
        <span v-if="scope.row.address">{{ scope.row.address }}</span>
        <span v-else class="text-muted">-</span>
      </template>
    </el-table-column>
    <el-table-column prop="product_count" label="产品数" width="100" align="center" sortable>
      <template #default="scope">
        <el-button 
          size="small" 
          type="primary"
          :disabled="scope.row.product_count === 0"
          @click="scope.row.product_count > 0 && $emit('manage-products', scope.row)"
        >
          {{ scope.row.product_count || 0 }}
        </el-button>
      </template>
    </el-table-column>
    <el-table-column prop="is_active" label="状态" width="100" align="center" sortable>
      <template #default="scope">
        <el-tag :type="scope.row.is_active ? 'success' : 'danger'" size="small">
          {{ scope.row.is_active ? '活跃' : '禁用' }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="created_at" label="创建时间" width="180" sortable>
      <template #default="scope">
        {{ formatDate(scope.row.created_at) }}
      </template>
    </el-table-column>
    <el-table-column label="操作" width="280" fixed="right" align="center">
      <template #default="scope">
        <el-button size="small" type="success" link @click="$emit('manage-products', scope.row)" :icon="Box">
          管理产品
        </el-button>
        <el-button size="small" type="primary" link @click="$emit('edit', scope.row)" :icon="Edit">
          编辑
        </el-button>
        <el-button size="small" type="danger" link @click="$emit('delete', scope.row.id)" :icon="Delete">
          删除
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import { User, Box, Edit, Delete } from '@element-plus/icons-vue';
import { formatDate } from '../../utils/dateFormat';

defineProps({
  clients: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  }
});

defineEmits(['selection-change', 'copy-phone', 'manage-products', 'edit', 'delete']);
</script>

<style scoped>
.company-name-cell {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.company-name {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  font-size: var(--font-size-base);
}

.text-muted {
  color: var(--text-placeholder);
  font-size: var(--font-size-xs);
}

.phone-link {
  color: var(--primary-color);
  cursor: pointer;
  text-decoration: none;
  transition: var(--transition-base);
}

.phone-link:hover {
  color: var(--primary-hover);
  text-decoration: underline;
}


.user-relation-info {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 11px;
  color: #909399;
}

.user-relation-info .el-icon {
  font-size: 12px;
}

.relation-hint {
  opacity: 0.7;
}

.key-text {
  font-family: monospace;
  font-size: 12px;
  color: var(--text-primary);
  word-break: break-all;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .el-table {
    font-size: var(--font-size-sm);
    min-width: 800px; /* 确保表格有最小宽度，可以横向滚动 */
  }
  
  .el-table :deep(.el-table__cell) {
    padding: var(--spacing-xs) var(--spacing-sm);
    word-break: break-word;
  }
  
  .el-table :deep(.el-table__header th),
  .el-table :deep(.el-table__body td) {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs);
  }
  
  .el-table :deep(.el-table__header-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .el-table :deep(.el-table__body-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  /* 表格容器优化 - 如果表格被包裹在卡片中 */
  :deep(.el-card__body) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
}
</style>

