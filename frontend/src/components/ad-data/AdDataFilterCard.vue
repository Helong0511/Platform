<!--
  广告数据详细报表 - 筛选区
  @file components/ad-data/AdDataFilterCard.vue
-->
<template>
  <el-card class="filter-card">
    <el-form :inline="true" :model="searchForm" class="filter-form">
      <el-form-item label="日期范围">
        <el-date-picker
          v-model="searchForm.dateRange"
          name="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          style="width: 100%;"
          @change="emit('date-range-change')"
        />
      </el-form-item>
      <el-form-item v-if="isAdmin" label="客户">
        <el-select
          v-model="searchForm.clientId"
          placeholder="全部客户"
          style="width: 100%;"
          clearable
          @change="emit('filter-client-change')"
        >
          <el-option
            v-for="user in users"
            :key="user.value"
            :label="user.label"
            :value="user.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="产品">
        <el-select
          v-model="searchForm.productId"
          placeholder="全部产品"
          style="width: 100%;"
          clearable
          @change="emit('filter-product-change')"
        >
          <el-option
            v-for="product in filterProducts"
            :key="product.value"
            :label="product.label"
            :value="product.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="国家">
        <el-select
          v-model="searchForm.countryCode"
          placeholder="全部区域"
          style="width: 100%;"
          clearable
          @change="emit('country-change')"
        >
          <el-option
            v-for="country in filterCountries"
            :key="country.code"
            :label="country.label || country.name_zh"
            :value="country.code"
          />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" :disabled="loading" @click="emit('fetch')">
          查询
        </el-button>
        <el-button :disabled="loading" @click="emit('reset')">重置</el-button>
      </el-form-item>
    </el-form>
    <div class="filter-hint">
      <el-icon :size="16"><InfoFilled /></el-icon>
      <span>默认查询数据是本月数据，如果要查询其它时间，请自行选择日期范围。</span>
    </div>
  </el-card>
</template>

<script setup>
import { InfoFilled } from '@element-plus/icons-vue';

defineProps({
  isAdmin: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  users: { type: Array, default: () => [] },
  filterProducts: { type: Array, default: () => [] },
  filterCountries: { type: Array, default: () => [] },
});

const searchForm = defineModel('searchForm', { type: Object, required: true });

const emit = defineEmits([
  'fetch',
  'reset',
  'date-range-change',
  'filter-client-change',
  'filter-product-change',
  'country-change',
]);
</script>

<style scoped>
.filter-hint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 8px;
  font-size: 13px;
  color: #909399;
}
</style>
