<template>
  <div class="daily-report-container">
    <div class="page-header">
      <div class="action-buttons">
        <el-button type="primary" @click="handleExport" :icon="Download">
          导出数据
        </el-button>
      </div>
    </div>

    <!-- 筛选控件 -->
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
            @change="handleDateRangeChange"
          ></el-date-picker>
        </el-form-item>
        <el-form-item v-if="isAdmin" label="客户">
          <el-select 
            v-model="searchForm.clientId" 
            name="clientId"
            placeholder="全部客户" 
            style="width: 100%;"
            @change="handleFilterClientChange"
            clearable
          >
            <el-option v-for="user in users" :key="user.value" :label="user.label" :value="user.value"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="产品">
          <el-select 
            v-model="searchForm.productId" 
            name="productId"
            placeholder="全部产品" 
            style="width: 100%;"
            clearable
          >
            <el-option v-for="product in filterProducts" :key="product.value" :label="product.label" :value="product.value"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchDailyData" :loading="loading" :disabled="loading">查询</el-button>
          <el-button @click="resetFilter" :disabled="loading">重置</el-button>
        </el-form-item>
      </el-form>
      <div class="filter-hint">
        <el-icon :size="16"><InfoFilled /></el-icon>
        <span>每日报表显示按产品每日汇总的数据，国家统一显示"全部区域"。默认查询本月数据。</span>
      </div>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="data-table-card">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-weight: 600; font-size: 16px;">每日报表数据</span>
          <el-button 
            type="text" 
            :icon="Setting" 
            @click="columnSettingVisible = true"
          >
            列设置
          </el-button>
        </div>
      </template>
      <el-table
        v-loading="loading"
        :data="dailyDataList"
        border
        stripe
        style="width: 100%"
        @sort-change="handleSortChange"
        :summary-method="getSummaries"
        show-summary
      >
        <el-table-column v-if="columnVisibility.date" prop="date" label="数据日期" sortable="custom"></el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.user_name" prop="user_name" label="所属客户"></el-table-column>
        <el-table-column v-if="columnVisibility.product_name" prop="product_name" label="产品名称" sortable="custom" sort-by="product" :min-width="150">
          <template #default="{ row }">
            <div class="product-name-cell" @click="handleProductClick(row)">
              <span class="product-name">{{ row.product_name }}</span>
              <el-icon class="product-icon"><Right /></el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.country_name_zh" prop="country_name_zh" label="国家"></el-table-column>
        <el-table-column v-if="columnVisibility.request_count" prop="request_count" label="请求数" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.match_count" prop="match_count" label="匹配数" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.coverage_rate" prop="coverage_rate" label="覆盖率" :formatter="formatPercentage" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.display_count" prop="display_count" label="展示数" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.display_rate" prop="display_rate" label="展示率" :formatter="formatPercentage" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.click_count" prop="click_count" label="点击数" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.click_rate" prop="click_rate" label="点击率" :formatter="formatPercentage" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.viewability_rate" prop="viewability_rate" label="可见率" :formatter="formatPercentage" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.cpc" prop="cpc" label="CPC" :formatter="formatCurrency" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.pageviews" prop="pageviews" label="PageViews" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.ecpm_after_deduct" prop="ecpm_after_deduct" :label="isAdmin ? 'eCPM(扣)' : 'eCPM'" :formatter="formatCurrency" sortable="custom"></el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.ecpm_before_deduct" prop="ecpm_before_deduct" label="eCPM" :formatter="formatCurrency" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.revenue_after_deduct" prop="revenue_after_deduct" :label="isAdmin ? '收益(扣)' : '收益'" :formatter="formatCurrency" sortable="custom"></el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.revenue_before_deduct" prop="revenue_before_deduct" label="收益" :formatter="formatCurrency" sortable="custom"></el-table-column>
      </el-table>

      <!-- 分页控件 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.size"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          :layout="isMobile ? 'total, prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
          class="pagination-component"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        ></el-pagination>
      </div>
    </el-card>

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="date" :disabled="true">数据日期（固定显示）</el-checkbox>
        <el-checkbox v-if="isAdmin" label="user_name">所属客户</el-checkbox>
        <el-checkbox label="product_name" :disabled="true">产品名称（固定显示）</el-checkbox>
        <el-checkbox label="country_name_zh">国家</el-checkbox>
        <el-checkbox label="request_count">请求数</el-checkbox>
        <el-checkbox label="match_count">匹配数</el-checkbox>
        <el-checkbox label="coverage_rate">覆盖率</el-checkbox>
        <el-checkbox label="display_count">展示数</el-checkbox>
        <el-checkbox label="display_rate">展示率</el-checkbox>
        <el-checkbox label="click_count">点击数</el-checkbox>
        <el-checkbox label="click_rate">点击率</el-checkbox>
        <el-checkbox label="viewability_rate">可见率</el-checkbox>
        <el-checkbox label="cpc">CPC</el-checkbox>
        <el-checkbox label="pageviews">PageViews</el-checkbox>
        <el-checkbox label="ecpm_after_deduct">eCPM(扣)</el-checkbox>
        <el-checkbox v-if="isAdmin" label="ecpm_before_deduct">eCPM</el-checkbox>
        <el-checkbox label="revenue_after_deduct">收益(扣)</el-checkbox>
        <el-checkbox v-if="isAdmin" label="revenue_before_deduct">收益</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>

    <!-- 产品管理对话框 -->
    <ProductManagementDialog
      v-model="productManagementVisible"
      :client-id="selectedClientId"
      :client-name="selectedClientName"
      :products="selectedClientProducts"
      :loading="loadingProducts"
      @refresh="handleProductManagementRefresh"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed, watch, nextTick } from 'vue';
import { useAuthStore } from '../../store';
import { ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem, ElSelect, ElOption, ElDatePicker, ElIcon, ElMessage, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus';
import { Download, InfoFilled, Setting, Right } from '@element-plus/icons-vue';
import { getDailySummary, exportAdData, getClientsWithData, getProductsWithData, getAdDataDateRange } from '../../api/adData';
import { useRouter } from 'vue-router';
import { extractErrorMessage, isErrorHandled } from '../../utils/api';
import { useDevice } from '../../composables/useDevice';
import ProductManagementDialog from '../../components/admin/ProductManagementDialog.vue';

// 路由实例
const router = useRouter();

// 获取用户认证状态
const authStore = useAuthStore();
const isAdmin = computed(() => authStore.isAdmin);

// 设备检测
const { isMobile } = useDevice();

// 状态管理
const dailyDataList = ref([]);
const filterProducts = ref([{ label: '全部产品', value: '' }]);
const users = ref([]);
const loading = ref(false);
const columnSettingVisible = ref(false);
const pagination = ref({
  current: 1,
  size: 10,
  total: 0
});

// 产品管理相关状态
const productManagementVisible = ref(false);
const selectedClientId = ref(null);
const selectedClientName = ref('');
const selectedClientProducts = ref([]);
const loadingProducts = ref(false);

// 排序状态
const sortInfo = ref({
  prop: 'date',
  order: 'descending' // 'ascending' 或 'descending'
});

// 筛选表单
const searchForm = ref({
  clientId: '',
  dateRange: [],
  productId: ''
});

// 列显示状态（默认全部显示）
const getDefaultColumnVisibility = () => ({
  date: true,  // 固定显示
  user_name: isAdmin.value,
  product_name: true,  // 固定显示
  country_name_zh: true,
  request_count: true,
  match_count: true,
  coverage_rate: true,
  display_count: true,
  display_rate: true,
  click_count: true,
  click_rate: true,
  viewability_rate: true,
  cpc: true,
  pageviews: true,
  ecpm_after_deduct: true,
  ecpm_before_deduct: isAdmin.value,
  revenue_after_deduct: true,
  revenue_before_deduct: isAdmin.value
});

const columnVisibility = reactive(getDefaultColumnVisibility());

// 计算属性：将对象转换为数组，用于 el-checkbox-group
const columnVisibilityArray = computed({
  get: () => {
    return Object.keys(columnVisibility).filter(key => columnVisibility[key])
  },
  set: (value) => {
    // 当 checkbox-group 的值变化时，更新对象
    Object.keys(columnVisibility).forEach(key => {
      columnVisibility[key] = value.includes(key)
    })
  }
})

// 从localStorage加载列显示设置
const loadColumnVisibility = () => {
  try {
    const saved = localStorage.getItem('dailyReport_columnVisibility');
    if (saved) {
      const savedVisibility = JSON.parse(saved);
      // 合并保存的设置和默认设置
      Object.assign(columnVisibility, getDefaultColumnVisibility(), savedVisibility);
      // 确保固定列始终显示
      columnVisibility.date = true;
      columnVisibility.product_name = true;
    }
  } catch (error) {
    console.error('加载列显示设置失败:', error);
  }
};

// 保存列显示设置到localStorage
const saveColumnVisibility = () => {
  try {
    // 只保存可调整的列，不保存固定列
    const toSave = {
      user_name: columnVisibility.user_name,
      country_name_zh: columnVisibility.country_name_zh,
      request_count: columnVisibility.request_count,
      match_count: columnVisibility.match_count,
      coverage_rate: columnVisibility.coverage_rate,
      display_count: columnVisibility.display_count,
      display_rate: columnVisibility.display_rate,
      click_count: columnVisibility.click_count,
      click_rate: columnVisibility.click_rate,
      viewability_rate: columnVisibility.viewability_rate,
      cpc: columnVisibility.cpc,
      pageviews: columnVisibility.pageviews,
      ecpm_after_deduct: columnVisibility.ecpm_after_deduct,
      ecpm_before_deduct: columnVisibility.ecpm_before_deduct,
      revenue_after_deduct: columnVisibility.revenue_after_deduct,
      revenue_before_deduct: columnVisibility.revenue_before_deduct
    };
    localStorage.setItem('dailyReport_columnVisibility', JSON.stringify(toSave));
    columnSettingVisible.value = false;
    ElMessage.success('列显示设置已保存');
  } catch (error) {
    console.error('保存列显示设置失败:', error);
    ElMessage.error('保存设置失败');
  }
};

// 格式化百分比
const formatPercentage = (row, column, value) => {
  const numValue = Number(value);
  if (isNaN(numValue)) {
    return '0.00%';
  }
  return `${numValue.toFixed(2)}%`;
};

// 格式化货币
const formatCurrency = (row, column, value) => {
  const numValue = Number(value);
  if (isNaN(numValue)) {
    return '$0.00';
  }
  return `$${numValue.toFixed(2)}`;
};

// 计算合计行
const getSummaries = (param) => {
  const { columns, data } = param;
  const sums = [];
  
  columns.forEach((column, index) => {
    if (index === 0) {
      sums[index] = '合计';
      return;
    }
    
    const prop = column.property;
    const values = data.map(item => Number(item[prop]) || 0);
    
    if (!values.every(value => isNaN(value))) {
      if (prop === 'request_count' || prop === 'match_count' || prop === 'display_count' || prop === 'click_count') {
        // 数值列：求和
        sums[index] = values.reduce((prev, curr) => {
          const value = Number(curr);
          if (!isNaN(value)) {
            return prev + curr;
          } else {
            return prev;
          }
        }, 0).toLocaleString();
      } else if (prop === 'cpc') {
        // CPC列：求和
        const sum = values.reduce((prev, curr) => {
          const value = Number(curr);
          if (!isNaN(value)) {
            return prev + curr;
          } else {
            return prev;
          }
        }, 0);
        sums[index] = `$${sum.toFixed(2)}`;
      } else if (prop === 'pageviews') {
        // PageViews列：求和
        sums[index] = values.reduce((prev, curr) => {
          const value = Number(curr);
          if (!isNaN(value)) {
            return prev + curr;
          } else {
            return prev;
          }
        }, 0).toLocaleString();
      } else if (prop === 'revenue_after_deduct' || prop === 'revenue_before_deduct') {
        // 收益列：求和
        const sum = values.reduce((prev, curr) => {
          const value = Number(curr);
          if (!isNaN(value)) {
            return prev + curr;
          } else {
            return prev;
          }
        }, 0);
        sums[index] = `$${sum.toFixed(2)}`;
      } else if (prop === 'coverage_rate') {
        // 覆盖率 = (匹配数总和 / 请求数总和) * 100
        const totalRequest = data.reduce((sum, item) => sum + (Number(item.request_count) || 0), 0);
        const totalMatch = data.reduce((sum, item) => sum + (Number(item.match_count) || 0), 0);
        const rate = totalRequest > 0 ? (totalMatch / totalRequest * 100) : 0;
        sums[index] = `${rate.toFixed(2)}%`;
      } else if (prop === 'display_rate') {
        // 展示率 = (展示数总和 / 匹配数总和) * 100
        const totalMatch = data.reduce((sum, item) => sum + (Number(item.match_count) || 0), 0);
        const totalDisplay = data.reduce((sum, item) => sum + (Number(item.display_count) || 0), 0);
        const rate = totalMatch > 0 ? (totalDisplay / totalMatch * 100) : 0;
        sums[index] = `${rate.toFixed(2)}%`;
      } else if (prop === 'click_rate') {
        // 点击率 = (点击数总和 / 展示数总和) * 100
        const totalDisplay = data.reduce((sum, item) => sum + (Number(item.display_count) || 0), 0);
        const totalClick = data.reduce((sum, item) => sum + (Number(item.click_count) || 0), 0);
        const rate = totalDisplay > 0 ? (totalClick / totalDisplay * 100) : 0;
        sums[index] = `${rate.toFixed(2)}%`;
      } else if (prop === 'viewability_rate') {
        // 可见率：使用加权平均（基于点击数）
        let totalWeighted = 0;
        let totalWeight = 0;
        data.forEach(item => {
          const viewabilityRate = Number(item.viewability_rate) || 0;
          const clickCount = Number(item.click_count) || 0;
          if (viewabilityRate > 0 && clickCount > 0) {
            totalWeighted += viewabilityRate * clickCount;
            totalWeight += clickCount;
          }
        });
        const rate = totalWeight > 0 ? (totalWeighted / totalWeight) : 0;
        sums[index] = `${rate.toFixed(2)}%`;
      } else if (prop === 'ecpm_after_deduct') {
        // eCPM(扣) = (收益(扣)总和 / 展示数总和) * 1000
        const totalDisplay = data.reduce((sum, item) => sum + (Number(item.display_count) || 0), 0);
        const totalRevenue = data.reduce((sum, item) => sum + (Number(item.revenue_after_deduct) || 0), 0);
        const ecpm = totalDisplay > 0 ? (totalRevenue / totalDisplay * 1000) : 0;
        sums[index] = `$${ecpm.toFixed(2)}`;
      } else if (prop === 'ecpm_before_deduct') {
        // eCPM = (收益总和 / 展示数总和) * 1000
        const totalDisplay = data.reduce((sum, item) => sum + (Number(item.display_count) || 0), 0);
        const totalRevenue = data.reduce((sum, item) => sum + (Number(item.revenue_before_deduct) || 0), 0);
        const ecpm = totalDisplay > 0 ? (totalRevenue / totalDisplay * 1000) : 0;
        sums[index] = `$${ecpm.toFixed(2)}`;
      } else {
        // 其他列（日期、客户、产品、国家）显示空
        sums[index] = '';
      }
    } else {
      sums[index] = '';
    }
  });
  
  return sums;
};

// 防抖定时器
let fetchDailyDataTimer = null;
// 当前正在进行的请求Promise（用于请求去重）
let currentRequestPromise = null;
// 当前请求的参数（用于判断是否为重复请求）
let currentRequestParams = null;

// 获取每日汇总数据
const fetchDailyData = async () => {
  // 如果正在加载，直接返回，防止重复请求
  if (loading.value) {
    return;
  }
  
  // 构建当前请求参数
  const params = {
    page: pagination.value.current,
    page_size: pagination.value.size
  };
  if (isAdmin.value && searchForm.value.clientId) {
    params.client_id = searchForm.value.clientId;
  }
  if (searchForm.value.productId) {
    params.product_id = searchForm.value.productId;
  }
  if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
    params.start_date = searchForm.value.dateRange[0];
    params.end_date = searchForm.value.dateRange[1];
  }
  
  // 添加排序参数
  if (sortInfo.value.prop) {
    params.sort_by = sortInfo.value.prop;
    params.sort_order = sortInfo.value.order === 'ascending' ? 'asc' : 'desc';
  }
  
  // 检查是否为重复请求（相同的参数且正在请求中）
  const paramsKey = JSON.stringify(params);
  if (currentRequestPromise && currentRequestParams === paramsKey) {
    // 相同的请求正在进行，等待现有请求完成
    try {
      await currentRequestPromise;
    } catch (error) {
      // 忽略错误，让现有请求处理
    }
    return;
  }
  
  // 清除之前的防抖定时器
  if (fetchDailyDataTimer) {
    clearTimeout(fetchDailyDataTimer);
  }
  
  // 设置防抖：300ms内只执行最后一次
  fetchDailyDataTimer = setTimeout(async () => {
    // 标记当前请求参数
    currentRequestParams = paramsKey;
    
    // 创建请求Promise
    const requestPromise = (async () => {
      try {
        loading.value = true;
        
        // 检查状态是否已认证（使用 authStore 而不是 sessionStorage）
        if (!authStore.isAuthenticated) {
          ElMessage.warning('登录已过期，请重新登录');
          router.push('/login').catch(() => {
            window.location.href = '/login';
          });
          return;
        }

        const response = await getDailySummary(params);
      
      // response已经是标准分页格式，直接使用data和total字段
      // getDailySummary使用paginated: true，失败时会抛出异常
      dailyDataList.value = response.data || [];
      
      // 确保total是数字类型，避免字符串类型导致的计算错误
      const totalValue = typeof response.total === 'number' ? response.total : parseInt(response.total || 0, 10);
      pagination.value.total = totalValue;
      
      // 如果没有数据且没有选择日期范围，尝试获取数据的日期范围并提示用户
      if (dailyDataList.value.length === 0 && pagination.value.total === 0 && 
          (!searchForm.value.dateRange || searchForm.value.dateRange.length === 0)) {
        try {
          const clientId = isAdmin.value && searchForm.value.clientId ? searchForm.value.clientId : null;
          const dateRange = await getAdDataDateRange(clientId);
          if (dateRange && dateRange.min_date && dateRange.max_date) {
            ElMessage.info({
              message: `当前月暂无数据。数据日期范围：${dateRange.min_date} 至 ${dateRange.max_date}，请选择对应的日期范围进行查询。`,
              duration: 10000,
              showClose: true
            });
          } else {
            ElMessage.warning({
              message: '当前月暂无数据。可能原因：1) 数据在其他月份，请选择日期范围查询；2) 产品未激活；3) 没有权限查看数据。',
              duration: 8000,
              showClose: true
            });
          }
        } catch (error) {
          // 如果获取日期范围失败，显示通用提示
          ElMessage.warning({
            message: '当前月暂无数据。如果数据在其他月份，请选择对应的日期范围进行查询。',
            duration: 6000,
            showClose: true
          });
        }
      }
      } catch (error) {
        if (error.response?.status === 401) {
          loading.value = false;
          return;
        }
        
        if (!isErrorHandled(error)) {
          const errorMsg = extractErrorMessage(error);
          ElMessage.error(errorMsg);
        }
      } finally {
        loading.value = false;
        // 清除当前请求标记
        if (currentRequestParams === paramsKey) {
          currentRequestPromise = null;
          currentRequestParams = null;
        }
      }
    })();
    
    // 保存当前请求Promise
    currentRequestPromise = requestPromise;
    
    // 等待请求完成
    await requestPromise;
  }, 300);
};

// 获取有数据的客户列表
const fetchClientsWithData = async () => {
  try {
    let startDate = null;
    let endDate = null;
    if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
      startDate = searchForm.value.dateRange[0];
      endDate = searchForm.value.dateRange[1];
    }
    
    const result = await getClientsWithData(startDate, endDate);
    const data = result.data || [];
    users.value = [
      { label: '全部客户', value: '' },
      ...data
        .filter(item => item && item.id != null)
        .map(item => ({
          label: item.full_name || '未知客户',
          value: item.id
        }))
    ];
  } catch (error) {
    users.value = [{ label: '全部客户', value: '' }];
  }
};

// 获取筛选表单的产品列表
const fetchFilterProducts = async (clientId) => {
  try {
    let startDate = null;
    let endDate = null;
    if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
      startDate = searchForm.value.dateRange[0];
      endDate = searchForm.value.dateRange[1];
    }
    
    const result = await getProductsWithData(clientId || null, startDate, endDate);
    const data = result.data || [];
    
    const productOptions = data
      .filter(item => item && item.id != null)
      .map(item => ({
        label: item.name || '未知产品',
        value: String(item.id),
        id: item.id
      }))
      .sort((a, b) => Number(b.id) - Number(a.id));
    
    filterProducts.value = [
      { label: '全部产品', value: '' },
      ...productOptions
    ];
  } catch (error) {
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
    filterProducts.value = [{ label: '全部产品', value: '' }];
  }
};

// 客户选择变化时的处理函数
const handleFilterClientChange = async (clientId) => {
  searchForm.value.productId = '';
  await fetchFilterProducts(clientId || null);
  
  // 修复选中值显示
  nextTick(() => {
    setTimeout(() => {
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100);
  });
};

// 日期范围变化时的处理函数
const handleDateRangeChange = async () => {
  if (isAdmin.value) {
    await fetchClientsWithData();
  }
  
  const clientId = searchForm.value.clientId || null;
  await fetchFilterProducts(clientId);
  
  if (searchForm.value.productId) {
    const productExists = filterProducts.value.some(p => p.value === searchForm.value.productId);
    if (!productExists) {
      searchForm.value.productId = '';
    }
  }
  
  // 修复选中值显示
  nextTick(() => {
    setTimeout(() => {
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100);
  });
};

// 处理排序变化
const handleSortChange = ({ prop, order }) => {
  if (prop) {
    // 处理特殊字段映射
    let sortProp = prop;
    if (prop === 'product_name') {
      sortProp = 'product'; // 后端使用 'product' 作为产品名称排序字段
    }
    
    sortInfo.value.prop = sortProp;
    sortInfo.value.order = order || 'descending';
    // 重置到第一页
    pagination.value.current = 1;
    // 重新获取数据
    fetchDailyData();
  }
};

// 重置筛选条件
const resetFilter = async () => {
  searchForm.value = {
    clientId: '',
    dateRange: [],
    productId: ''
  };
  pagination.value.current = 1;
  // 重置排序
  sortInfo.value = {
    prop: 'date',
    order: 'descending'
  };
  
  if (isAdmin.value) {
    await fetchClientsWithData();
  }
  
  const defaultClientId = isAdmin.value ? null : null;
  await fetchFilterProducts(defaultClientId);
  
  fetchDailyData();
};

// 分页处理
const handleSizeChange = (size) => {
  pagination.value.size = size;
  pagination.value.current = 1;  // 分页大小变化时重置到第一页
  fetchDailyData();
};

const handlePageChange = (page) => {
  pagination.value.current = page;
  fetchDailyData();
};

// 导出数据
const handleExport = async () => {
  try {
    if (pagination.value.total === 0) {
      ElMessage.warning('当前没有可导出的数据，请先查询数据');
      return;
    }
    
    const params = {};
    
    if (isAdmin.value && searchForm.value.clientId) {
      params.client_id = parseInt(searchForm.value.clientId);
    }
    
    if (searchForm.value.productId) {
      params.product_id = parseInt(searchForm.value.productId);
    }

    if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
      params.start_date = searchForm.value.dateRange[0];
      params.end_date = searchForm.value.dateRange[1];
    }
    
    // 注意：导出功能暂时使用详细报表的导出，因为每日汇总的导出需要单独实现
    await exportAdData(params);
    ElMessage.success('导出成功');
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
  }
};

// 监听分页变化
let isInitializing = true;

watch(
  () => [pagination.value.current, pagination.value.size],
  ([newCurrent, newSize], [oldCurrent, oldSize]) => {
    if (isInitializing) {
      return;
    }
    
    if (oldCurrent === undefined || oldSize === undefined) {
      return;
    }
    
    if (newCurrent !== oldCurrent && newSize === oldSize) {
      fetchDailyData();
    } else if (newSize !== oldSize) {
      if (newCurrent !== 1) {
        pagination.value.current = 1;
      } else {
        fetchDailyData();
      }
    }
  },
  { flush: 'post' }
);

// 加载页面数据
const loadPageData = async () => {
  try {
    // 检查认证状态，如果token过期，直接返回
    if (!authStore.isAuthenticated) {
      // token不存在或已过期，跳转到登录页
      ElMessage.warning('登录已过期，请重新登录');
      router.push('/login').catch(() => {
        window.location.href = '/login';
      });
      return;
    }
    
    await fetchDailyData();
    
    if (isAdmin.value) {
      await fetchClientsWithData();
    }
    
    const defaultClientId = isAdmin.value ? null : null;
    await fetchFilterProducts(defaultClientId);
  } catch (error) {
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(`页面初始化失败: ${errorMsg}`);
    }
  }
};

// 页面挂载时加载数据
onMounted(async () => {
  // 加载列显示设置
  loadColumnVisibility();
  await nextTick();
  setTimeout(async () => {
    await loadPageData();
    await nextTick();
    isInitializing = false;
  }, 0);
});

// 组件卸载时清理定时器
onUnmounted(() => {
  if (fetchDailyDataTimer) {
    clearTimeout(fetchDailyDataTimer);
    fetchDailyDataTimer = null;
  }
  // 清理请求标记
  currentRequestPromise = null;
  currentRequestParams = null;
});

// 处理产品点击事件
const handleProductClick = (row) => {
  // 设置选中的客户信息
  selectedClientId.value = row.client_id || authStore.userInfo?.id;
  selectedClientName.value = row.user_name || authStore.userInfo?.full_name || '未知客户';
  // 显示产品管理对话框
  productManagementVisible.value = true;
};

// 处理产品管理刷新事件
const handleProductManagementRefresh = () => {
  // 产品管理对话框关闭时刷新数据
  fetchDailyData();
};
</script>

<style scoped>
.daily-report-container {
  width: 100%;
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-xl);
  padding: var(--spacing-xl);
  background-color: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.action-buttons {
  display: flex;
  gap: var(--spacing-md);
}

.filter-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.filter-form {
  margin-bottom: 0;
}

.filter-form :deep(.el-form-item) {
  width: 300px;
  margin-bottom: var(--spacing-lg);
}

.filter-form :deep(.el-form-item:last-child) {
  width: auto;
}

.filter-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background-color: var(--primary-light);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  color: var(--primary-color);
  font-size: var(--font-size-sm);
}

.pagination-container {
  margin-top: var(--spacing-lg);
  padding: var(--spacing-lg) 0;
  text-align: right;
  border-top: 1px solid var(--border-lighter);
}

.data-table-card {
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
  overflow: hidden;
}

.data-table-card :deep(.el-card__body) {
  padding: var(--spacing-xl);
}

/* 移动端优化 */
@media (max-width: 767px) {
  .daily-report-container {
    padding: var(--spacing-md);
  }
  
  .page-header {
    flex-direction: column;
    align-items: stretch;
    gap: var(--spacing-md);
    padding: var(--spacing-md);
    margin-bottom: var(--spacing-md);
  }
  
  .action-buttons {
    flex-direction: column;
    width: 100%;
    gap: var(--spacing-sm);
  }
  
  .action-buttons .el-button {
    width: 100%;
    min-height: var(--touch-target-size);
  }
  
  .filter-card {
    margin-bottom: var(--spacing-md);
  }
  
  .filter-card :deep(.el-card__body) {
    padding: var(--spacing-md);
  }
  
  .filter-form {
    display: flex !important;
    flex-direction: column !important;
  }
  
  .filter-form :deep(.el-form--inline) {
    display: flex !important;
    flex-direction: column !important;
  }
  
  .filter-form :deep(.el-form-item) {
    width: 100% !important;
    margin-right: 0 !important;
    margin-bottom: var(--spacing-md) !important;
    display: flex !important;
    flex-direction: column !important;
  }
  
  .filter-form :deep(.el-form-item__label) {
    width: 100% !important;
    text-align: left !important;
    margin-bottom: var(--spacing-xs) !important;
    padding: 0 !important;
    margin-right: 0 !important;
    float: none !important;
    justify-content: flex-start !important;
    align-items: flex-start !important;
    display: block !important;
    font-weight: var(--font-weight-semibold);
    color: var(--text-primary);
  }
  
  .filter-form :deep(.el-form-item__content) {
    width: 100% !important;
    margin-left: 0 !important;
    flex: 1 !important;
  }
  
  .filter-form :deep(.el-input),
  .filter-form :deep(.el-select),
  .filter-form :deep(.el-date-editor),
  .filter-form :deep(.el-date-picker) {
    width: 100% !important;
    max-width: 100% !important;
  }
  
  .filter-form :deep(.el-input__wrapper) {
    min-height: var(--touch-target-size);
    width: 100% !important;
  }
  
  .filter-form :deep(.el-select .el-input__wrapper) {
    min-height: var(--touch-target-size);
    width: 100% !important;
  }
  
  .filter-form :deep(.el-date-editor.el-input__wrapper) {
    width: 100% !important;
    min-height: var(--touch-target-size);
  }
  
  /* 日期选择器特殊处理 */
  .filter-form :deep(.el-date-editor) {
    width: 100% !important;
  }
  
  .filter-form :deep(.el-date-editor .el-range-separator) {
    width: auto !important;
    padding: 0 var(--spacing-xs);
  }
  
  .filter-form :deep(.el-date-editor .el-range-input) {
    width: calc(50% - 20px) !important;
    flex: 1 !important;
  }
  
  /* 查询和重置按钮移动端优化 */
  .filter-form :deep(.el-form-item:last-child) {
    display: flex !important;
    flex-direction: row !important;
    gap: var(--spacing-sm);
    margin-top: var(--spacing-sm);
    margin-bottom: 0 !important;
    width: 100% !important;
  }
  
  .filter-form :deep(.el-form-item:last-child .el-form-item__label) {
    display: none !important;
  }
  
  .filter-form :deep(.el-form-item:last-child .el-form-item__content) {
    width: 100% !important;
    display: flex !important;
    flex-direction: row !important;
    gap: var(--spacing-sm);
    margin-left: 0 !important;
  }
  
  .filter-form :deep(.el-form-item:last-child .el-button) {
    flex: 1;
    min-height: var(--touch-target-size);
    width: auto;
    white-space: nowrap;
  }
  
  .filter-hint {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs) var(--spacing-sm);
    line-height: 1.5;
  }
  
  .pagination-container {
    text-align: center;
    padding: var(--spacing-md) 0;
  }
  
  /* 移动端表格卡片优化 - 支持横向滚动 */
  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  /* 移动端表格优化 */
  .el-table {
    font-size: var(--font-size-sm);
    min-width: 800px; /* 确保表格有最小宽度，可以横向滚动 */
  }
  
  .el-table :deep(.el-table__cell) {
    padding: var(--spacing-xs) var(--spacing-sm);
    word-break: break-word;
  }
  
  .el-table :deep(.el-table__header th),
  .el-table :deep(.el-table__body td) {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs);
  }
  
  /* 确保表格列内容不换行，通过横向滚动查看完整内容 */
  .el-table :deep(.el-table__body td) {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  
  /* 文本列（产品名称、客户名称、国家）在移动端允许适当换行以节省空间 */
  .el-table :deep(.el-table__body tr td:nth-child(3)), /* 产品名称 */
  .el-table :deep(.el-table__body tr td:nth-child(4)) { /* 国家 */
    white-space: normal;
    word-break: break-word;
    max-width: 100px;
    min-width: 80px;
  }
  
  /* 管理员模式下，所属客户列也允许换行 */
  .el-table :deep(.el-table__body tr td:nth-child(2)) {
    white-space: normal;
    word-break: break-word;
    max-width: 100px;
    min-width: 80px;
  }
  
  .el-table :deep(.el-table__header-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .el-table :deep(.el-table__body-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  /* 移动端分页组件优化 */
  .pagination-component {
    flex-wrap: wrap;
    justify-content: center;
    font-size: var(--font-size-sm);
  }
  
  .pagination-component :deep(.el-pagination__total) {
    margin-right: var(--spacing-sm);
    font-size: var(--font-size-sm);
  }
  
  .pagination-component :deep(.btn-prev),
  .pagination-component :deep(.btn-next),
  .pagination-component :deep(.el-pager li) {
    min-width: var(--touch-target-size);
    min-height: var(--touch-target-size);
    font-size: var(--font-size-sm);
  }
}
/* 产品名称单元格样式 */
.product-name-cell {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  cursor: pointer;
  padding: var(--spacing-xs) 0;
  transition: all 0.2s ease;
}

.product-name-cell:hover {
  color: var(--primary-color);
}

.product-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-icon {
  font-size: var(--font-size-sm);
  opacity: 0.6;
  transition: opacity 0.2s ease;
}

.product-name-cell:hover .product-icon {
  opacity: 1;
}
</style>

