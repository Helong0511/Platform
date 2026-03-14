<!--
Offer 筛选组件
从 OfferManagement.vue 拆分
负责高级筛选功能
-->
<template>
  <el-card class="offer-filter-card">
    <template #header>
      <div class="card-header">
        <span class="title">高级筛选</span>
        <el-button link type="primary" @click="handleToggleExpand">
          {{ expanded ? '收起' : '展开' }}
          <el-icon class="el-icon--right">
            <ArrowUp v-if="expanded" />
            <ArrowDown v-else />
          </el-icon>
        </el-button>
      </div>
    </template>

    <el-collapse-transition>
      <el-form
        v-show="expanded"
        :model="filterData"
        label-width="120px"
        size="default"
      >
        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="创建时间">
              <el-date-picker
                v-model="filterData.created_from"
                type="date"
                placeholder="开始日期"
                value-format="YYYY-MM-DD"
                class="w-100"
              />
            </el-form-item>
          </el-col>

          <el-col :span="8">
            <el-form-item label="至">
              <el-date-picker
                v-model="filterData.created_to"
                type="date"
                placeholder="结束日期"
                value-format="YYYY-MM-DD"
                class="w-100"
              />
            </el-form-item>
          </el-col>

          <el-col :span="8">
            <el-form-item label="价格范围">
              <el-input-number
                v-model="filterData.price_min"
                :min="0"
                placeholder="最低价"
                class="w-50"
              />
              <span class="range-separator">-</span>
              <el-input-number
                v-model="filterData.price_max"
                :min="0"
                placeholder="最高价"
                class="w-50"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="包含渠道">
              <el-select
                v-model="filterData.publisher_ids"
                multiple
                placeholder="选择渠道"
                class="w-100"
                filterable
              >
                <el-option
                  v-for="pub in publishers"
                  :key="pub.id"
                  :label="pub.publisher_name"
                  :value="pub.id"
                />
              </el-select>
            </el-form-item>
          </el-col>

          <el-col :span="8">
            <el-form-item label="Cap 状态">
              <el-select
                v-model="filterData.cap_status"
                placeholder="全部"
                clearable
                class="w-100"
              >
                <el-option label="正常" value="normal" />
                <el-option label="接近限制" value="warning" />
                <el-option label="已达限制" value="exceeded" />
              </el-select>
            </el-form-item>
          </el-col>

          <el-col :span="8">
            <el-form-item label="排序">
              <el-select
                v-model="filterData.sort_by"
                placeholder="选择排序"
                class="w-100"
              >
                <el-option label="创建时间" value="created_at" />
                <el-option label="更新时间" value="updated_at" />
                <el-option label="价格" value="price" />
                <el-option label="名称" value="offer_name" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item>
              <el-button type="primary" @click="handleApply">
                <el-icon><Search /></el-icon>
                应用筛选
              </el-button>
              <el-button @click="handleReset">
                <el-icon><Refresh /></el-icon>
                重置
              </el-button>
              <el-button @click="handleSaveFilter">
                <el-icon><Star /></el-icon>
                保存筛选条件
              </el-button>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-collapse-transition>
  </el-card>
</template>

<script setup>
import { ref, reactive } from 'vue';
import { ArrowUp, ArrowDown, Search, Refresh, Star } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

// Props
const props = defineProps({
  publishers: {
    type: Array,
    default: () => []
  }
});

// Emits
const emit = defineEmits(['apply', 'reset']);

// 状态
const expanded = ref(false);

// 筛选数据
const filterData = reactive({
  created_from: '',
  created_to: '',
  price_min: null,
  price_max: null,
  publisher_ids: [],
  cap_status: '',
  sort_by: 'created_at'
});

// 切换展开/收起
const handleToggleExpand = () => {
  expanded.value = !expanded.value;
};

// 应用筛选
const handleApply = () => {
  emit('apply', { ...filterData });
  ElMessage.success('筛选条件已应用');
};

// 重置
const handleReset = () => {
  Object.assign(filterData, {
    created_from: '',
    created_to: '',
    price_min: null,
    price_max: null,
    publisher_ids: [],
    cap_status: '',
    sort_by: 'created_at'
  });
  emit('reset');
  ElMessage.success('筛选条件已重置');
};

// 保存筛选条件
const handleSaveFilter = () => {
  // TODO: 保存到本地存储或后端
  ElMessage.info('保存筛选条件功能开发中');
};

// 导出
defineExpose({
  reset: handleReset,
  apply: handleApply
});
</script>

<style scoped>
.offer-filter-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-size: 16px;
  font-weight: bold;
}

.w-100 {
  width: 100%;
}

.w-50 {
  width: 45%;
}

.range-separator {
  margin: 0 8px;
}
</style>
