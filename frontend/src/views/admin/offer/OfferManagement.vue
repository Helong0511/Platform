<!--
Offer 管理主页面（重构版）
协调各子组件：列表、表单、统计、筛选
-->
<template>
  <div class="offer-management">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>Offer 管理</h2>
      <el-button type="primary" @click="handleCreate">
        <el-icon><Plus /></el-icon>
        新建 Offer
      </el-button>
    </div>

    <!-- 筛选组件 -->
    <OfferFilter
      ref="filterRef"
      :publishers="publishers"
      @apply="handleFilterApply"
      @reset="handleFilterReset"
    />

    <!-- 列表组件 -->
    <OfferList
      ref="listRef"
      @create="handleCreate"
      @edit="handleEdit"
      @view="handleView"
      @delete="handleDelete"
    />

    <!-- 统计组件 -->
    <OfferStats
      v-if="selectedOfferId"
      :offer-id="selectedOfferId"
    />

    <!-- 表单对话框 -->
    <OfferForm
      v-model="formVisible"
      :offer-id="selectedOfferId"
      @success="handleFormSuccess"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import OfferList from './OfferList.vue';
import OfferForm from './OfferForm.vue';
import OfferStats from './OfferStats.vue';
import OfferFilter from './OfferFilter.vue';
import { getPublishers } from '@/api/publisher';

// 组件引用
const filterRef = ref(null);
const listRef = ref(null);

// 状态
const formVisible = ref(false);
const selectedOfferId = ref(null);
const publishers = ref([]);

// 加载渠道列表
const loadPublishers = async () => {
  try {
    const response = await getPublishers();
    publishers.value = response.data.data || [];
  } catch (error) {
    console.error('加载渠道列表失败:', error);
  }
};

// 创建 Offer
const handleCreate = () => {
  selectedOfferId.value = null;
  formVisible.value = true;
};

// 编辑 Offer
const handleEdit = (row) => {
  selectedOfferId.value = row.id;
  formVisible.value = true;
};

// 查看 Offer
const handleView = (row) => {
  selectedOfferId.value = row.id;
  ElMessage.info(`查看 Offer: ${row.offer_name}`);
  // TODO: 打开详情对话框或跳转详情页
};

// 删除 Offer
const handleDelete = async (row) => {
  // 列表组件已处理，这里可以添加额外逻辑
  console.log('删除 Offer:', row.id);
};

// 筛选应用
const handleFilterApply = (filters) => {
  console.log('应用筛选:', filters);
  // TODO: 传递给列表组件
};

// 筛选重置
const handleFilterReset = () => {
  console.log('重置筛选');
  if (listRef.value) {
    listRef.value.refresh();
  }
};

// 表单成功
const handleFormSuccess = () => {
  if (listRef.value) {
    listRef.value.refresh();
  }
  selectedOfferId.value = null;
};

// 初始化
onMounted(() => {
  loadPublishers();
});
</script>

<style scoped>
.offer-management {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  color: #303133;
}
</style>
