<!--
  广告数据报表 - 筛选区（详细报表 / 每日报表共用）
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
      <el-form-item v-if="showDimension" label="统计维度">
        <el-select
          v-model="searchForm.dimension"
          style="width: 100%;"
          @change="emit('dimension-change')"
        >
          <el-option
            v-for="item in dimensionOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item v-if="showCountry" label="国家">
        <el-select
          v-model="searchForm.countryCode"
          placeholder="全部国家"
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
      <el-form-item v-if="showAdUnit" label="广告单元">
        <el-select
          v-model="searchForm.adUnit"
          placeholder="全部广告单元"
          style="width: 100%;"
          clearable
          filterable
          @change="emit('ad-unit-change')"
        >
          <el-option
            v-for="unit in filterAdUnits"
            :key="unit.value"
            :label="unit.label"
            :value="unit.value"
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
      <span>{{ hintText }}</span>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue';
import { InfoFilled } from '@element-plus/icons-vue';
import {
  AD_DATA_DIMENSION_HINTS,
  AD_DATA_DIMENSION_OPTIONS,
  DEFAULT_AD_DATA_DIMENSION,
  showAdUnitFilterForDimension,
  showCountryFilterForDimension
} from '../../constants/adDataDimension';

const props = defineProps({
  isAdmin: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  users: { type: Array, default: () => [] },
  filterProducts: { type: Array, default: () => [] },
  filterCountries: { type: Array, default: () => [] },
  filterAdUnits: { type: Array, default: () => [] },
  showDimension: { type: Boolean, default: true },
  defaultHint: {
    type: String,
    default: '默认查询数据是本月数据，如果要查询其它时间，请自行选择日期范围。'
  }
});

const searchForm = defineModel('searchForm', { type: Object, required: true });

const emit = defineEmits([
  'fetch',
  'reset',
  'date-range-change',
  'filter-client-change',
  'filter-product-change',
  'dimension-change',
  'country-change',
  'ad-unit-change'
]);

const dimensionOptions = AD_DATA_DIMENSION_OPTIONS;

const showCountry = computed(() =>
  props.showDimension
    ? showCountryFilterForDimension(searchForm.value.dimension || DEFAULT_AD_DATA_DIMENSION)
    : true
);

const showAdUnit = computed(() =>
  props.showDimension &&
  showAdUnitFilterForDimension(searchForm.value.dimension || DEFAULT_AD_DATA_DIMENSION)
);

const hintText = computed(() => {
  if (!props.showDimension) {
    return props.defaultHint;
  }
  const dimension = searchForm.value.dimension || DEFAULT_AD_DATA_DIMENSION;
  const dimensionHint = AD_DATA_DIMENSION_HINTS[dimension] || '';
  return `${dimensionHint} ${props.defaultHint}`;
});
</script>

<style scoped>
.filter-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.filter-form {
  margin-bottom: 0;
}

.filter-form :deep(.el-form-item) {
  width: 340px;
  margin-bottom: var(--spacing-lg);
  margin-right: 16px;
  vertical-align: top;
  display: inline-flex;
  align-items: center;
}

.filter-form :deep(.el-form-item:first-child) {
  width: 400px;
}

.filter-form :deep(.el-form-item:last-child) {
  width: auto;
  margin-right: 0;
}

.filter-form :deep(.el-form-item__label) {
  width: auto;
  min-width: 80px;
  flex-shrink: 0;
  text-align: right;
  padding-right: 12px;
  line-height: 32px;
}

.filter-form :deep(.el-form-item__content) {
  flex: 1;
  min-width: 200px;
  line-height: 32px;
}

.filter-form :deep(.el-input),
.filter-form :deep(.el-select),
.filter-form :deep(.el-date-editor) {
  width: 100%;
}

.filter-form :deep(.el-input__wrapper),
.filter-form :deep(.el-select .el-input__wrapper) {
  min-height: 32px;
}

.filter-hint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 8px;
  font-size: 13px;
  color: #909399;
  line-height: 1.5;
}

@media (max-width: 767px) {
  .filter-card {
    margin-bottom: var(--spacing-md);
  }

  .filter-card :deep(.el-card__body) {
    padding: var(--spacing-md);
  }

  .filter-form {
    display: flex;
    flex-direction: column;
  }

  .filter-form :deep(.el-form--inline) {
    display: flex;
    flex-direction: column;
  }

  .filter-form :deep(.el-form-item),
  .filter-form :deep(.el-form-item:first-child) {
    width: 100%;
    margin-right: 0;
    margin-bottom: var(--spacing-md);
    flex-direction: column;
    align-items: stretch;
  }

  .filter-form :deep(.el-form-item__label) {
    width: 100%;
    min-width: 0;
    text-align: left;
    padding-right: 0;
    margin-bottom: var(--spacing-xs);
  }

  .filter-form :deep(.el-form-item__content) {
    width: 100%;
    min-width: 0;
    margin-left: 0;
  }

  .filter-form :deep(.el-input),
  .filter-form :deep(.el-select),
  .filter-form :deep(.el-date-editor) {
    width: 100%;
  }

  .filter-form :deep(.el-form-item:last-child) {
    flex-direction: row;
    gap: var(--spacing-sm);
    margin-bottom: 0;
  }

  .filter-form :deep(.el-form-item:last-child .el-form-item__content) {
    display: flex;
    gap: var(--spacing-sm);
  }

  .filter-form :deep(.el-form-item:last-child .el-button) {
    flex: 1;
    min-height: var(--touch-target-size);
  }
}
</style>
