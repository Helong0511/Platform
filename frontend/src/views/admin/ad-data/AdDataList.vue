<!-- 广告数据列表组件 -->
<template>
  <div class="ad-data-list">
    <el-card class="filter-card">
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
      <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total,prev,pager,next" @current-change="loadData" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';
import { getAdData } from '@/api/adData';
import { getProducts } from '@/api/product';

const filterForm = reactive({ product_id: null, date_range: [] });
const data = ref([]);
const products = ref([]);
const loading = ref(false);
const page = ref(1);
const total = ref(0);

const loadData = async () => {
  loading.value = true;
  try {
    const response = await getAdData({ ...filterForm, page: page.value });
    data.value = response.data.data || [];
    total.value = response.data.total || 0;
  } catch (error) { console.error(error); }
  finally { loading.value = false; }
};

const loadProducts = async () => {
  try { const res = await getProducts(); products.value = res.data.data || []; }
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
