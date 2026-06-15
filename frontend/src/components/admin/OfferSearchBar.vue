<!--
  Offer 列表筛选栏
  @file components/admin/OfferSearchBar.vue
-->
<template>
  <div class="search-bar">
    <el-input
      v-model="searchKeyword"
      placeholder="搜索Offer名称或ID"
      clearable
      style="width: 300px;"
      @clear="emit('search')"
      @keyup.enter="emit('search')"
    >
      <template #prefix>
        <el-icon><Search /></el-icon>
      </template>
    </el-input>
    <el-select
      v-if="isAdmin"
      v-model="filterAdvertiser"
      placeholder="请选择广告主"
      clearable
      filterable
      style="width: 180px; margin-left: 10px; min-width: 180px;"
      @change="emit('advertiser-change')"
    >
      <el-option
        v-for="adv in advertiserList"
        :key="adv.id"
        :label="adv.advertiser_name"
        :value="adv.id"
      />
    </el-select>
    <el-select
      v-model="filterStatus"
      placeholder="请选择状态"
      clearable
      style="width: 140px; margin-left: 10px; min-width: 140px;"
      @change="emit('status-change')"
    >
      <el-option label="全部" :value="null" />
      <el-option label="Active" value="Active" />
      <el-option label="Inactive" value="Inactive" />
    </el-select>
    <el-select
      v-model="filterActive"
      placeholder="请选择激活状态"
      clearable
      style="width: 160px; margin-left: 10px; min-width: 160px;"
      @change="emit('active-change')"
    >
      <el-option label="全部" :value="null" />
      <el-option label="激活" :value="true" />
      <el-option label="禁用" :value="false" />
    </el-select>
    <el-select
      v-if="isAdmin"
      v-model="filterPublisher"
      placeholder="分配渠道"
      clearable
      filterable
      style="width: 180px; margin-left: 10px; min-width: 180px;"
      @change="emit('publisher-change')"
    >
      <el-option
        v-for="pub in publisherList"
        :key="pub.id"
        :label="pub.publisher_name"
        :value="pub.id"
      />
    </el-select>
    <el-button type="primary" :icon="Search" style="margin-left: 10px;" @click="emit('search')">
      搜索
    </el-button>
    <el-button :icon="Refresh" @click="emit('reset')">重置</el-button>
  </div>
</template>

<script setup>
import { Search, Refresh } from '@element-plus/icons-vue';

defineProps({
  isAdmin: { type: Boolean, default: false },
  advertiserList: { type: Array, default: () => [] },
  publisherList: { type: Array, default: () => [] },
});

const searchKeyword = defineModel('searchKeyword', { type: String, default: '' });
const filterAdvertiser = defineModel('filterAdvertiser', { default: null });
const filterStatus = defineModel('filterStatus', { default: null });
const filterActive = defineModel('filterActive', { default: null });
const filterPublisher = defineModel('filterPublisher', { default: null });

const emit = defineEmits([
  'search',
  'reset',
  'advertiser-change',
  'status-change',
  'active-change',
  'publisher-change',
]);
</script>

<style scoped>
.search-bar {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 10px;
}

.search-bar :deep(.el-input__wrapper) {
  padding-right: 30px;
}

.search-bar :deep(.el-select .el-input__wrapper) {
  padding-right: 30px;
}
</style>
