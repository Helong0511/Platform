<template>
  <el-card class="filter-card" shadow="never">
    <el-form :inline="true" :model="modelValue" class="filter-form" label-width="90px">
      <el-form-item label="公司名称">
        <el-input 
          :model-value="modelValue.company_name"
          @update:model-value="updateValue('company_name', $event)"
          placeholder="输入公司名称"
          clearable
          style="width: 200px;"
          @clear="handleClear"
        ></el-input>
      </el-form-item>
      <el-form-item label="状态">
        <el-select 
          :model-value="modelValue.is_active"
          @update:model-value="updateValue('is_active', $event)"
          placeholder="全部状态"
          clearable
          style="width: 150px;"
          aria-label="选择客户状态"
        >
          <el-option label="全部" :value="null"></el-option>
          <el-option label="活跃" :value="true"></el-option>
          <el-option label="禁用" :value="false"></el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="创建日期">
        <el-date-picker
          :model-value="modelValue.dateRange"
          @update:model-value="updateValue('dateRange', $event)"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          style="width: 240px;"
          clearable
        ></el-date-picker>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch" :icon="Search">查询</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { ElCard, ElForm, ElFormItem, ElInput, ElSelect, ElOption, ElDatePicker, ElButton, ElIcon } from 'element-plus';
import { Search } from '@element-plus/icons-vue';

const props = defineProps({
  modelValue: {
    type: Object,
    required: true,
    default: () => ({
      company_name: '',
      is_active: null,
      dateRange: []
    })
  }
});

const emit = defineEmits(['update:modelValue', 'search', 'reset']);

const updateValue = (key, value) => {
  emit('update:modelValue', { ...props.modelValue, [key]: value });
};

const handleSearch = () => {
  emit('search');
};

const handleReset = () => {
  emit('reset');
};

const handleClear = () => {
  updateValue('company_name', '');
  emit('search');
};
</script>

<style scoped>
.filter-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.filter-card :deep(.el-card__body) {
  padding: var(--spacing-xl);
}

.filter-form {
  margin-bottom: 0;
}

.filter-form :deep(.el-form-item) {
  margin-bottom: var(--spacing-lg);
}

.filter-form :deep(.el-form-item__label) {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  font-size: var(--font-size-base);
}

@media (max-width: 767px) {
  .filter-form {
    display: flex;
    flex-direction: column;
  }

  .filter-form :deep(.el-form-item) {
    width: 100%;
    margin-right: 0;
  }
}
</style>

