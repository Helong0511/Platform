<!--
  产品管理操作栏
  @file components/admin/ProductActionBar.vue
-->
<template>
  <div class="action-bar">
    <div class="action-left">
      <el-button
        type="primary"
        size="large"
        class="add-button"
        :icon="Plus"
        @click="emit('add')"
      >
        添加产品
      </el-button>
    </div>
    <div class="action-right">
      <el-tag type="info" size="large" effect="dark">
        共 {{ productCount }} 个产品
      </el-tag>
    </div>
  </div>
</template>

<script setup>
import { ElButton, ElTag } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import '../../styles/product-management-dialog.css';

defineProps({
  productCount: { type: Number, default: 0 },
});

const emit = defineEmits(['add']);
</script>
