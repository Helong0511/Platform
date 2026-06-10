<!--
  产品管理弹窗页头
  @file components/admin/ProductDialogHeader.vue
-->
<template>
  <div class="dialog-header">
    <div class="header-content">
      <div class="header-left">
        <el-icon class="header-icon"><Box /></el-icon>
        <div class="header-text">
          <h4 class="header-title">{{ clientName }}</h4>
          <p class="header-subtitle">产品管理</p>
        </div>
      </div>
      <div class="header-right">
        <el-statistic :value="productCount" title="产品总数">
          <template #prefix>
            <el-icon :size="20"><Box /></el-icon>
          </template>
        </el-statistic>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ElIcon, ElStatistic } from 'element-plus';
import { Box } from '@element-plus/icons-vue';
import '../../styles/product-management-dialog.css';

defineProps({
  clientName: { type: String, default: '未知客户' },
  productCount: { type: Number, default: 0 },
});
</script>
