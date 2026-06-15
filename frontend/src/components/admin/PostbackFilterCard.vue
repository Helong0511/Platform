<!--
  Postback 转化管理 - 筛选区
  @file components/admin/PostbackFilterCard.vue
-->
<template>
  <el-card class="filter-card" shadow="never">
    <el-form :inline="true" :model="searchForm" class="filter-form">
      <el-form-item label="平台">
        <el-select
          v-model="searchForm.platform"
          placeholder="全部"
          clearable
          style="width: 150px;"
          name="platform"
          popper-class="select-dropdown"
          :teleported="true"
        >
          <el-option label="全部" value="" />
          <el-option label="BFT" value="bft" />
        </el-select>
      </el-form-item>
      <el-form-item label="转化ID/点击ID">
        <el-input
          v-model="searchForm.conversion_or_click_id"
          placeholder="输入转化ID或点击ID"
          clearable
          style="width: 200px;"
          name="conversion_or_click_id"
          @keyup.enter="emit('search')"
        >
          <template #prefix>
            <el-icon :size="16"><Search /></el-icon>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="产品ID">
        <el-input-number
          v-model="searchForm.product_id"
          placeholder="产品ID"
          clearable
          :min="1"
          style="width: 150px;"
          name="product_id"
        />
      </el-form-item>
      <el-form-item label="客户ID">
        <el-input-number
          v-model="searchForm.client_id"
          placeholder="客户ID"
          clearable
          :min="1"
          style="width: 150px;"
          name="client_id"
        />
      </el-form-item>
      <el-form-item label="Click ID">
        <el-input
          v-model="searchForm.click_id"
          placeholder="Click ID"
          clearable
          style="width: 200px;"
          name="click_id"
          @keyup.enter="emit('search')"
        >
          <template #prefix>
            <el-icon :size="16"><Search /></el-icon>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="Offer">
        <el-select
          v-model="searchForm.offer_id"
          placeholder="请选择Offer"
          clearable
          filterable
          style="width: 200px;"
          name="offer_id"
        >
          <el-option
            v-for="offer in offerList"
            :key="offer.id"
            :label="`${offer.id} - ${offer.offer_name}`"
            :value="offer.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="渠道">
        <el-select
          v-model="searchForm.publisher_id"
          placeholder="请选择渠道"
          clearable
          filterable
          style="width: 200px;"
          name="publisher_id"
        >
          <el-option
            v-for="pub in publisherList"
            :key="pub.id"
            :label="pub.publisher_name"
            :value="pub.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="广告主">
        <el-select
          v-model="searchForm.advertiser_id"
          placeholder="请选择广告主"
          clearable
          filterable
          style="width: 200px;"
          name="advertiser_id"
        >
          <el-option
            v-for="adv in advertiserList"
            :key="adv.id"
            :label="adv.advertiser_name"
            :value="adv.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="转化状态">
        <el-select
          v-model="searchForm.conversion_status"
          placeholder="全部"
          clearable
          style="width: 150px;"
          name="conversion_status"
        >
          <el-option label="Approved" value="Approved" />
          <el-option label="Pending" value="Pending" />
        </el-select>
      </el-form-item>
      <el-form-item label="时间范围" class="date-range-item">
        <el-date-picker
          v-model="dateRange"
          name="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          style="width: 300px;"
          class="date-picker-full"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" :icon="Search" @click="emit('search')">
          查询
        </el-button>
        <el-button :icon="Refresh" @click="emit('reset')">重置</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { Search, Refresh } from '@element-plus/icons-vue';

defineProps({
  loading: { type: Boolean, default: false },
  offerList: { type: Array, default: () => [] },
  publisherList: { type: Array, default: () => [] },
  advertiserList: { type: Array, default: () => [] },
});

const searchForm = defineModel('searchForm', { type: Object, required: true });
const dateRange = defineModel('dateRange', { type: Array, default: () => [] });

const emit = defineEmits(['search', 'reset']);
</script>
