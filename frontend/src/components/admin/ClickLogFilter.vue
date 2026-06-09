<!--
  点击日志筛选表单
  @file components/admin/ClickLogFilter.vue
-->
<template>
  <!-- 筛选区 -->
  <div class="click-log-filter">
    <el-collapse v-model="filterCollapse" class="filter-collapse">
      <el-collapse-item name="filter" :title="filterCollapse.includes('filter') ? '收起筛选条件' : '展开筛选条件'">
        <div class="filter-bar">
          <div class="filter-row">
            <el-input
              v-model="localFilters.clickId"
              placeholder="Click ID"
              clearable
              class="filter-item"
              @clear="handleClear"
              @keyup.enter="handleSearch"
              @input="handleInput"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-select
              v-model="localFilters.offer"
              placeholder="请选择Offer"
              clearable
              filterable
              class="filter-item"
              @change="handleSearch"
            >
              <el-option
                v-for="offer in offerList"
                :key="offer.id"
                :label="`${offer.id} - ${offer.offer_name}`"
                :value="offer.id"
              />
            </el-select>
            <el-select
              v-model="localFilters.publisher"
              placeholder="请选择渠道"
              clearable
              filterable
              class="filter-item"
              @change="handleSearch"
            >
              <el-option
                v-for="pub in publisherList"
                :key="pub.id"
                :label="pub.publisher_name"
                :value="pub.id"
              />
            </el-select>
            <el-input
              v-model="localFilters.ip"
              placeholder="IP地址（支持精确匹配或前缀，如：192.168.）"
              clearable
              class="filter-item"
              @clear="handleClear"
              @keyup.enter="handleSearch"
              @input="handleInput"
            />
            <el-input
              v-model="localFilters.country"
              placeholder="国家"
              clearable
              class="filter-item filter-item-small"
              @clear="handleClear"
              @keyup.enter="handleSearch"
              @input="handleInput"
            />
          </div>
          <div class="filter-row">
            <el-date-picker
              v-model="localFilters.dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              class="filter-item filter-item-date"
              @change="handleDateChange"
            />
            <div class="filter-actions">
              <el-button type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
              <el-button :icon="Refresh" @click="handleReset">重置</el-button>
            </div>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue';
import { Search, Refresh } from '@element-plus/icons-vue';

const props = defineProps({
  filters: {
    type: Object,
    required: true
  },
  offerList: {
    type: Array,
    default: () => []
  },
  publisherList: {
    type: Array,
    default: () => []
  }
});

const emit = defineEmits(['update:filters', 'search', 'reset']);

const filterCollapse = ref(['filter']);

// 本地过滤器状态
const localFilters = ref({
  clickId: props.filters.clickId || '',
  offer: props.filters.offer || null,
  publisher: props.filters.publisher || null,
  ip: props.filters.ip || '',
  country: props.filters.country || '',
  dateRange: props.filters.dateRange || []
});

// 监听props变化
watch(() => props.filters, (newFilters) => {
  localFilters.value = {
    clickId: newFilters.clickId || '',
    offer: newFilters.offer || null,
    publisher: newFilters.publisher || null,
    ip: newFilters.ip || '',
    country: newFilters.country || '',
    dateRange: newFilters.dateRange || []
  };
}, { deep: true });

// 防抖定时器
let debounceTimer = null;

const handleInput = () => {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(() => {
    emit('search');
  }, 500);
};

const handleClear = () => {
  emit('search');
};

const handleDateChange = () => {
  emit('search');
};

const handleSearch = () => {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  emit('update:filters', { ...localFilters.value });
  emit('search');
};

const handleReset = () => {
  localFilters.value = {
    clickId: '',
    offer: null,
    publisher: null,
    ip: '',
    country: '',
    dateRange: []
  };
  emit('update:filters', { ...localFilters.value });
  emit('reset');
};
</script>

<style scoped>
.click-log-filter {
  margin-bottom: 16px;
}

.filter-collapse {
  border: none;
}

.filter-bar {
  padding: 16px;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}

.filter-row:last-child {
  margin-bottom: 0;
}

.filter-item {
  flex: 1;
  min-width: 150px;
}

.filter-item-small {
  min-width: 120px;
  max-width: 150px;
}

.filter-item-date {
  min-width: 300px;
  max-width: 400px;
}

.filter-actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 768px) {
  .filter-item {
    min-width: 100%;
  }
  
  .filter-item-small {
    min-width: 100%;
    max-width: 100%;
  }
  
  .filter-item-date {
    min-width: 100%;
    max-width: 100%;
  }
}
</style>
