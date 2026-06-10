<!--
  产品管理列表表格
  @file components/admin/ProductTable.vue
-->
<template>
  <div class="table-wrapper">
    <el-table
      v-loading="loading"
      :data="products"
      border
      stripe
      class="product-table"
      :max-height="tableMaxHeight"
      empty-text="暂无产品数据，点击添加产品开始创建"
      :header-cell-style="{
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        color: '#fff',
        fontWeight: 'bold',
        fontSize: '14px',
        height: '44px',
        padding: '10px 0',
      }"
    >
      <el-table-column prop="id" label="ID" :width="isMobile ? 40 : 80" align="center" class-name="id-column">
        <template #default="scope">
          <el-tag type="info" effect="plain" :size="isMobile ? 'small' : 'small'">{{ scope.row.id }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="产品名称" :min-width="isMobile ? 120 : 300" class-name="name-column">
        <template #default="scope">
          <div class="product-name-cell">
            <el-icon class="product-icon"><Box /></el-icon>
            <span class="product-name">{{ scope.row.name }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="ecpm_deduct_ratio" :label="isMobile ? 'eCPM' : 'eCPM减扣比例'" :width="isMobile ? 65 : 120" align="center" class-name="ecpm-column">
        <template #default="scope">
          <el-tag type="warning" effect="dark" :size="isMobile ? 'small' : 'default'">
            {{ formatPercentage(scope.row.ecpm_deduct_ratio) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="revenue_deduct_ratio" :label="isMobile ? '收益' : '收益减扣比例'" :width="isMobile ? 60 : 100" align="center" class-name="revenue-column">
        <template #default="scope">
          <el-tag type="success" effect="dark" :size="isMobile ? 'small' : 'default'">
            {{ formatPercentage(scope.row.revenue_deduct_ratio) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态" :width="isMobile ? 60 : 80" align="center" class-name="status-column">
        <template #default="scope">
          <el-tag
            :type="scope.row.is_active ? 'success' : 'danger'"
            :size="isMobile ? 'small' : 'default'"
            effect="dark"
            :icon="scope.row.is_active ? CircleCheck : CircleClose"
          >
            {{ scope.row.is_active ? '活跃' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" :label="isMobile ? '时间' : '创建时间'" :width="isMobile ? 100 : 180" align="center" class-name="time-column">
        <template #default="scope">
          <div class="time-cell">
            <el-icon :size="isMobile ? 14 : 16"><Clock /></el-icon>
            <span>{{ formatDate(scope.row.created_at) }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" :width="isMobile ? 100 : 280" fixed="right" align="center" class-name="action-column">
        <template #default="scope">
          <div class="action-buttons" :class="{ 'mobile-actions': isMobile }">
            <el-button
              type="info"
              :size="isMobile ? 'small' : 'default'"
              :icon="Clock"
              class="action-btn history-btn"
              :circle="isMobile"
              :title="isMobile ? '历史' : ''"
              @click="emit('history', scope.row)"
            >
              <span v-if="!isMobile">历史</span>
            </el-button>
            <el-button
              type="primary"
              :size="isMobile ? 'small' : 'default'"
              :icon="Edit"
              class="action-btn edit-btn"
              :circle="isMobile"
              :title="isMobile ? '编辑' : ''"
              @click="emit('edit', scope.row)"
            >
              <span v-if="!isMobile">编辑</span>
            </el-button>
            <el-button
              type="danger"
              :size="isMobile ? 'small' : 'default'"
              :icon="Delete"
              class="action-btn delete-btn"
              :circle="isMobile"
              :title="isMobile ? '删除' : ''"
              @click="emit('delete', scope.row.id)"
            >
              <span v-if="!isMobile">删除</span>
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ElButton, ElIcon, ElTable, ElTableColumn, ElTag } from 'element-plus';
import { Box, CircleCheck, CircleClose, Clock, Delete, Edit } from '@element-plus/icons-vue';
import { formatDate } from '../../utils/dateFormat';
import { formatRatioAsPercent as formatPercentage } from '../../utils/percentFormat';
import '../../styles/product-management-dialog.css';

defineProps({
  products: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  isMobile: { type: Boolean, default: false },
  tableMaxHeight: { type: Number, default: 400 },
});

const emit = defineEmits(['history', 'edit', 'delete']);
</script>
