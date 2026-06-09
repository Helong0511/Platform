<!--
  广告数据列表组件（AdDataList.vue）

  作为广告数据模块的子组件，负责：
  1. 多维筛选：产品、客户、日期、平台等
  2. 数据表格：分页展示广告明细，支持列显隐
  3. 导出：按当前筛选条件导出 Excel

  筛选联动与表格格式化由对应 composable 提供。
-->
<template>
  <!-- 页面主模板 -->
  <!-- 页面主模板 -->
<div class="ad-data-list">
    <!-- 筛选区 -->
    <el-card class="filter-card">
      <!-- 表单区域 -->
      <el-form :model="filterForm" :inline="true">
        <el-form-item label="产品">
          <el-select v-model="filterForm.product_id" placeholder="全部" clearable filterable>
            <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="filterForm.date_range" type="daterange" range-separator="至" start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
    <el-card class="table-card">
      <!-- 数据表格 -->
      <el-table v-loading="loading" :data="data" border>
        <el-table-column prop="date" label="日期" width="120" />
        <el-table-column prop="product_name" label="产品" min-width="150" />
        <el-table-column prop="request_count" label="请求数" width="100" />
        <el-table-column prop="match_count" label="匹配数" width="100" />
        <el-table-column prop="display_count" label="展示数" width="100" />
        <el-table-column prop="click_count" label="点击数" width="100" />
        <el-table-column prop="ecpm_after_deduct" label="eCPM" width="100" />
        <el-table-column prop="revenue_after_deduct" label="收益" width="100" />
      </el-table>
      <!-- 分页 -->
      <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total,prev,pager,next" @current-change="loadData" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';
import { getAdDataList } from '@/api/ad-data';
import { getProductList } from '@/api/product';

const filterForm = reactive({ product_id: null, date_range: [] });
const data = ref([]);
const products = ref([]);
const loading = ref(false);
const page = ref(1);
const total = ref(0);

const loadData = async () => {
  loading.value = true;
  try {
    const response = await getAdDataList({ ...filterForm, page: page.value });
    data.value = response.data || [];
    total.value = response.total || 0;
  } catch (error) { console.error(error); }
  finally { loading.value = false; }
};

const loadProducts = async () => {
  try {
    const res = await getProductList({ page_size: 100 });
    products.value = res.data || [];
  }
  catch (error) { console.error(error); }
};

const handleSearch = () => { page.value = 1; loadData(); };
const handleReset = () => { Object.assign(filterForm, { product_id: null, date_range: [] }); page.value = 1; loadData(); };

onMounted(() => { loadProducts(); loadData(); });
</script>

<style scoped>
.ad-data-list { padding: 20px; }
.filter-card { margin-bottom: 20px; }
.table-card { margin-top: 20px; }
</style>
