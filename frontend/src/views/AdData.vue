<template>
  <div class="ad-data-container">
    <div class="page-header">
      <div class="action-buttons">
        <el-button 
          type="primary" 
          @click="handleExport" 
          :icon="Download"
          :size="isMobile ? 'default' : 'default'"
        >
          导出数据
        </el-button>
        <el-button 
          v-if="isAdmin && selectedRows.length > 0" 
          type="danger" 
          @click="handleBatchDelete" 
          :icon="Delete"
          :size="isMobile ? 'default' : 'default'"
        >
          <span v-if="!isMobile">批量删除 ({{ selectedRows.length }})</span>
          <span v-else>批量删除</span>
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
            placeholder="全部产品" 
            style="width: 100%;"
            clearable
            @change="handleFilterProductChange"
          >
            <el-option v-for="product in filterProducts" :key="product.value" :label="product.label" :value="product.value"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="国家">
          <el-select 
            v-model="searchForm.countryCode" 
            placeholder="全部区域" 
            style="width: 100%;"
            clearable
            @change="handleCountryChange"
          >
            <el-option v-for="country in filterCountries" :key="country.code" :label="country.name_zh" :value="country.code"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchAdData" :loading="loading" :disabled="loading">查询</el-button>
          <el-button @click="resetFilter" :disabled="loading">重置</el-button>
        </el-form-item>
      </el-form>
      <div class="filter-hint">
        <el-icon :size="16"><InfoFilled /></el-icon>
        <span>默认查询数据是本月数据，如果要查询其它时间，请自行选择日期范围。</span>
      </div>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="data-table-card">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-weight: 600; font-size: 16px;">详细报表数据</span>
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
        :data="adDataList"
        border
        stripe
        style="width: 100%"
        @selection-change="handleSelectionChange"
        @sort-change="handleSortChange"
        :summary-method="getSummaries"
        show-summary
      >
        <el-table-column type="selection" width="55"></el-table-column>
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
        <el-table-column v-if="isAdmin" label="操作" width="180">
          <template #default="scope">
            <el-button size="small" type="primary" @click="handleEdit(scope.row)">修改</el-button>
            <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
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
        ></el-pagination>
      </div>
    </el-card>

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="editDialogVisible"
      title="编辑广告数据"
      :width="isMobile ? '95%' : '600px'"
      :append-to-body="true"
    >
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" :label-width="isMobile ? '0' : '140px'" class="edit-form">
        <el-form-item label="数据日期" prop="date">
          <el-date-picker
            v-model="editForm.date"
            name="date"
            type="date"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%;"
            disabled
          ></el-date-picker>
        </el-form-item>
        <el-form-item label="所属用户" prop="client_id">
          <el-select 
            v-model="editForm.client_id" 
            placeholder="选择用户" 
            style="width: 100%;"
          >
            <el-option v-for="user in users" :key="user.value" :label="user.label" :value="user.value"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="产品" prop="product_id">
          <el-select 
            v-model="editForm.product_id" 
            placeholder="选择产品" 
            style="width: 100%;" 
            @change="handleProductChange" 
            :disabled="!editForm.client_id"
          >
            <el-option v-for="product in products" :key="product.value" :label="product.label" :value="product.value"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="国家" prop="country_code">
          <el-input 
            v-model="editForm.country_code" 
            name="country_code"
            placeholder="输入国家代码（如：US、USA、840、United States of America、美国）"
            style="width: 100%;"
          >
            <template #append>
              <el-button @click="handleCountryCodeHelp" title="查看帮助">?</el-button>
            </template>
          </el-input>
          <div class="form-tip" style="margin-top: 5px; font-size: 12px; color: #909399;">
            支持格式：二字母代码（US）、三字母代码（USA）、数字代码（840）、英文名称（United States of America）、中文名称（美国）
          </div>
        </el-form-item>
        <el-form-item label="请求数" prop="request_count">
          <el-input v-model.number="editForm.request_count" name="request_count" type="number" min="0" placeholder="请输入请求数"></el-input>
        </el-form-item>
        <el-form-item label="匹配数" prop="match_count">
          <el-input v-model.number="editForm.match_count" name="match_count" type="number" min="0" placeholder="请输入匹配数"></el-input>
        </el-form-item>
        <el-form-item label="展示数" prop="display_count">
          <el-input v-model.number="editForm.display_count" name="display_count" type="number" min="0" placeholder="请输入展示数"></el-input>
        </el-form-item>
        <el-form-item label="点击数" prop="click_count">
          <el-input v-model.number="editForm.click_count" name="click_count" type="number" min="0" placeholder="请输入点击数"></el-input>
        </el-form-item>
        <el-form-item label="点击率" prop="click_rate">
          <el-input v-model.number="editForm.click_rate" name="click_rate" type="number" step="0.01" min="0" placeholder="请输入点击率"></el-input>
        </el-form-item>
        <el-form-item label="可见率" prop="viewability_rate">
          <el-input v-model.number="editForm.viewability_rate" name="viewability_rate" type="number" step="0.01" min="0" placeholder="请输入可见率"></el-input>
        </el-form-item>
        <el-form-item label="CPC" prop="cpc">
          <el-input v-model.number="editForm.cpc" name="cpc" type="number" step="0.01" min="0" placeholder="请输入CPC"></el-input>
        </el-form-item>
        <el-form-item label="PageViews" prop="pageviews">
          <el-input v-model.number="editForm.pageviews" name="pageviews" type="number" min="0" placeholder="请输入PageViews"></el-input>
        </el-form-item>
        <el-form-item label="eCPM(扣)" prop="ecpm_after_deduct">
          <el-input v-model.number="editForm.ecpm_after_deduct" name="ecpm_after_deduct" type="number" step="0.01" min="0" placeholder="请输入扣除后的eCPM"></el-input>
        </el-form-item>
        <el-form-item label="eCPM" prop="ecpm_before_deduct">
          <el-input v-model.number="editForm.ecpm_before_deduct" name="ecpm_before_deduct" type="number" step="0.01" min="0" placeholder="请输入eCPM"></el-input>
        </el-form-item>
        <el-form-item label="收益(扣)" prop="revenue_after_deduct">
          <el-input v-model.number="editForm.revenue_after_deduct" name="revenue_after_deduct" type="number" step="0.01" min="0" placeholder="请输入扣除后的收益"></el-input>
        </el-form-item>
        <el-form-item label="收益" prop="revenue_before_deduct">
          <el-input v-model.number="editForm.revenue_before_deduct" name="revenue_before_deduct" type="number" step="0.01" min="0" placeholder="请输入收益"></el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="cancelEdit">取消</el-button>
          <el-button type="primary" @click="saveEdit">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      :append-to-body="true"
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
import { useAuthStore } from '../store';
import { ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem, ElSelect, ElOption, ElDatePicker, ElTag, ElIcon, ElLoading, ElMessage, ElMessageBox, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus';
import { Download, Search, Delete, InfoFilled, Setting, Right } from '@element-plus/icons-vue';
import { getAdDataList, exportAdData, getProductsForSelect, getClientsWithData, getProductsWithData, getCountriesWithData, updateAdData, getProductById, deleteAdData, batchDeleteAdData, getAdDataDateRange } from '../api/adData';
import { useRouter, useRoute } from 'vue-router';
import { getSuccessMessage, getWarningMessage } from '../utils/messages';
import { extractErrorMessage, isErrorHandled, ensureCsrfToken } from '../utils/api';
import { useDevice } from '../composables/useDevice';
import ProductManagementDialog from '../components/admin/ProductManagementDialog.vue';

// 路由实例
const router = useRouter();
const route = useRoute();

// 获取用户认证状态
const authStore = useAuthStore();
const isAdmin = computed(() => authStore.isAdmin);

// 设备检测
const { isMobile, isTablet, isDesktop } = useDevice();

// 状态管理
const adDataList = ref([]);
const products = ref([]); // 编辑对话框使用的产品列表
const filterProducts = ref([{ label: '全部产品', value: '' }]); // 筛选表单使用的产品列表，初始化为至少包含"全部产品"选项
const filterCountries = ref([{ code: '', name_zh: '全部区域' }]); // 筛选表单使用的国家列表
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
  clientId: '', // 筛选表单的客户ID（仅管理员可见）
  dateRange: [],
  productId: '',
  countryCode: '' // 国家代码筛选
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
    const saved = localStorage.getItem('adData_columnVisibility');
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
    localStorage.setItem('adData_columnVisibility', JSON.stringify(toSave));
    columnSettingVisible.value = false;
    ElMessage.success('列显示设置已保存');
  } catch (error) {
    console.error('保存列显示设置失败:', error);
    ElMessage.error('保存设置失败');
  }
};

// 格式化百分比
// 注意：后端返回的比率已经是百分比形式（如85.5表示85.5%），所以不需要再乘以100
const formatPercentage = (row, column, value) => {
  // value 已经是百分比数值（如85.5），直接添加%符号即可
  // 确保始终显示两位小数，不足两位用0补齐
  const numValue = Number(value);
  if (isNaN(numValue)) {
    return '0.00%';
  }
  return `${numValue.toFixed(2)}%`;
};

// 格式化货币
const formatCurrency = (row, column, value) => {
  // 确保始终显示两位小数，不足两位用0补齐
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
      // 第一列是选择框，显示"合计"
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
        // CPC列：按公式计算
        // 管理员登录：CPC = 收益（扣前）/ 点击数
        // 客户端登录：CPC = 收益（扣后）/ 点击数
        const totalClick = data.reduce((sum, item) => sum + (Number(item.click_count) || 0), 0);
        let totalRevenue = 0;
        if (isAdmin.value) {
          // 管理员：使用收益（扣前）
          totalRevenue = data.reduce((sum, item) => sum + (Number(item.revenue_before_deduct) || 0), 0);
        } else {
          // 客户端：使用收益（扣后）
          totalRevenue = data.reduce((sum, item) => sum + (Number(item.revenue_after_deduct) || 0), 0);
        }
        const cpc = totalClick > 0 ? (totalRevenue / totalClick) : 0;
        sums[index] = `$${cpc.toFixed(2)}`;
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
        // 其他列（日期、客户、产品、国家、操作）显示空
        sums[index] = '';
      }
    } else {
      sums[index] = '';
    }
  });
  
  return sums;
};

// 防抖定时器
let fetchAdDataTimer = null;
// 当前正在进行的请求Promise（用于请求去重）
let currentRequestPromise = null;
// 当前请求的参数（用于判断是否为重复请求）
let currentRequestParams = null;

// 获取广告数据
const fetchAdData = async () => {
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
  if (searchForm.value.countryCode) {
    params.country_code = searchForm.value.countryCode;
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
  if (fetchAdDataTimer) {
    clearTimeout(fetchAdDataTimer);
  }
  
  // 设置防抖：300ms内只执行最后一次
  fetchAdDataTimer = setTimeout(async () => {
    // 标记当前请求参数
    currentRequestParams = paramsKey;
    
    // 创建请求Promise
    const requestPromise = (async () => {
      try {
        loading.value = true;
        
        // 检查状态是否已认证
        if (!authStore.isAuthenticated) {
          ElMessage.warning('登录已过期，请重新登录');
          router.push('/login').catch(() => {
            window.location.href = '/login';
          });
          return;
        }

        const response = await getAdDataList(params);
      
      // response已经是标准分页格式，直接使用data和total字段
      // getAdDataList使用paginated: true，失败时会抛出异常
      adDataList.value = response.data || [];
      
      // 确保total是数字类型，避免字符串类型导致的计算错误
      const totalValue = typeof response.total === 'number' ? response.total : parseInt(response.total || 0, 10);
      pagination.value.total = totalValue;
      
      // 如果没有数据且没有选择日期范围，尝试获取数据的日期范围并提示用户
      if (adDataList.value.length === 0 && pagination.value.total === 0 && 
          (!searchForm.value.dateRange || searchForm.value.dateRange.length === 0)) {
        try {
          const clientId = isAdmin.value && searchForm.value.clientId ? searchForm.value.clientId : null;
          const dateRange = await getAdDataDateRange(clientId);
          if (dateRange && dateRange.min_date && dateRange.max_date) {
            ElMessage.info({
              message: `当前月暂无数据。数据日期范围：${dateRange.min_date} 至 ${dateRange.max_date}，请选择对应的日期范围进行查询。`,
              duration: 8000,
              showClose: true
            });
          } else {
            ElMessage.info({
              message: '当前月暂无数据。如果数据在其他月份，请选择对应的日期范围进行查询。',
              duration: 5000,
              showClose: true
            });
          }
        } catch (error) {
          // 如果获取日期范围失败，显示通用提示
          ElMessage.info({
            message: '当前月暂无数据。如果数据在其他月份，请选择对应的日期范围进行查询。',
            duration: 5000,
            showClose: true
          });
        }
      }
      
        // 验证数据完整性
        if (adDataList.value.length > 0) {
          const requiredFields = ['date', 'product_name', 'request_count', 'match_count'];
          const missingFields = requiredFields.filter(field => !(field in adDataList.value[0]));
          if (missingFields.length > 0) {
            ElMessage.warning(`数据格式不完整，缺少字段: ${missingFields.join(', ')}`);
          }
        }
      } catch (error) {
        // 401错误已在拦截器中处理，直接返回
        if (error.response?.status === 401) {
          loading.value = false;
          return;
        }
        
        // 检查错误是否已被处理（如拦截器或API函数已显示）
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

// 获取有数据的客户列表（用于筛选）
const fetchClientsWithData = async () => {
  try {
    // 获取当前日期范围（用于筛选客户）
    let startDate = null;
    let endDate = null;
    if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
      startDate = searchForm.value.dateRange[0];
      endDate = searchForm.value.dateRange[1];
    }
    
    const result = await getClientsWithData(startDate, endDate);
    const data = result.data || [];
    // 转换为下拉选择格式，添加"全部客户"选项
    users.value = [
      { label: '全部客户', value: '' },
      ...data
        .filter(item => item && item.id != null) // 过滤掉无效的客户
        .map(item => ({
          label: item.full_name || '未知客户',
          value: item.id
        }))
    ];
  } catch (error) {
    // 静默失败，使用默认值
    users.value = [{ label: '全部客户', value: '' }];
  }
};

// 获取产品列表（用于筛选）
const fetchProducts = async (clientId) => {
  try {
    const data = await getProductsForSelect(clientId);
    // 移除label中的编号前缀
    products.value = data.map(item => ({
      value: item.value,
      label: item.label.replace(/^\d+\s*-\s*/, '')
    }));
  } catch (error) {
    // 静默失败，使用空数组
    products.value = [];
  }
};

// 获取筛选表单的产品列表（只显示有数据的产品）
/**
 * 获取筛选条件中的产品列表
 * 
 * 逻辑说明：
 * 1. 默认显示本月数据：
 *    - 客户=全部客户 → 产品=本月全部产品（可选择）
 *    - 客户=特定客户 → 产品=该客户本月全部产品（可选择）
 * 
 * 2. 选择了日期范围：
 *    - 客户=全部客户 → 产品=该日期范围全部产品（可选择）
 *    - 客户=特定客户 → 产品=该客户该日期范围全部产品（可选择）
 * 
 * @param {string|null} clientId - 客户ID，null表示全部客户
 */
const fetchFilterProducts = async (clientId) => {
  try {
    // 获取当前日期范围（用于筛选产品）
    // 如果没有选择日期范围，后端会默认使用本月数据
    let startDate = null;
    let endDate = null;
    if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
      startDate = searchForm.value.dateRange[0];
      endDate = searchForm.value.dateRange[1];
    }
    
    // 调用API获取产品列表
    // - clientId = null（全部客户）→ 获取所有客户的产品
    // - clientId = 具体值 → 只获取该客户的产品
    // - 日期范围：如果选择了日期范围，使用该范围；否则后端默认使用本月数据
    const result = await getProductsWithData(clientId || null, startDate, endDate);
    const data = result.data || [];
    
    // 转换为下拉选择格式，按 id 倒序排序
    const productOptions = data
      .filter(item => item && item.id != null) // 过滤掉无效的产品
      .map(item => ({
        label: item.name || '未知产品',
        value: String(item.id),
        id: item.id // 保留 id 用于排序
      }))
      .sort((a, b) => {
        // 按产品 id 倒序排序（从大到小）
        return Number(b.id) - Number(a.id);
      });
    
    // 添加"全部产品"选项到最前面
    filterProducts.value = [
      { label: '全部产品', value: '' },
      ...productOptions
    ];
  } catch (error) {
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
    // 确保至少有一个"全部产品"选项
    filterProducts.value = [{ label: '全部产品', value: '' }];
  }
};

/**
 * 客户选择变化时的处理函数
 * 
 * 当客户选择变化时：
 * - 清空当前产品选择和国家选择
 * - 重新加载产品列表（根据选择的客户和当前日期范围）
 * - 重新加载国家列表（根据选择的客户和当前日期范围）
 * 
 * @param {string|null} clientId - 选择的客户ID，null或空字符串表示全部客户
 */
const handleFilterClientChange = async (clientId) => {
  // 清空产品选择和国家选择
  searchForm.value.productId = '';
  searchForm.value.countryCode = '';
  
  // 重新加载产品列表
  await fetchFilterProducts(clientId || null);
  
  // 重新加载国家列表（清空产品后，国家列表基于客户和日期范围）
  await fetchFilterCountries(clientId || null, null);
  
  // 修复选中值显示
  nextTick(() => {
    setTimeout(() => {
      // 强制更新 el-select 状态，确保选中值正确显示
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100)
  })
};

/**
 * 筛选表单产品选择变化时的处理函数
 * 
 * 当筛选表单的产品选择变化时：
 * - 重新加载国家列表（根据当前客户、产品和日期范围）
 */
const handleFilterProductChange = async () => {
  const clientId = searchForm.value.clientId || null;
  const productId = searchForm.value.productId ? parseInt(searchForm.value.productId) : null;
  
  // 重新加载国家列表
  await fetchFilterCountries(clientId, productId);
  
  // 如果当前选择的国家不在新列表中，清空国家选择
  if (searchForm.value.countryCode) {
    const countryExists = filterCountries.value.some(c => c.code === searchForm.value.countryCode);
    if (!countryExists) {
      searchForm.value.countryCode = '';
    }
  }
  
  // 修复选中值显示
  nextTick(() => {
    setTimeout(() => {
      // 强制更新 el-select 状态，确保选中值正确显示
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100)
  })
};

/**
 * 获取筛选表单的国家列表（只显示有数据的国家）
 */
const fetchFilterCountries = async (clientId = null, productId = null) => {
  try {
    // 获取当前日期范围（用于筛选国家）
    let startDate = null;
    let endDate = null;
    if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
      startDate = searchForm.value.dateRange[0];
      endDate = searchForm.value.dateRange[1];
    }
    
    // 调用API获取国家列表
    const result = await getCountriesWithData(clientId, productId, startDate, endDate);
    const data = result.data || [];
    
    // 转换为下拉选择格式
    // 过滤掉code为空、null或'ZZ'的项，避免重复的"全部区域"选项
    // 'ZZ'是后端返回的"全部区域"代码，前端使用空字符串''表示"全部区域"
    const countryOptions = data
      .filter(item => item && item.code != null && item.code !== '' && item.code !== 'ZZ')
      .map(item => ({
        code: item.code,
        name_zh: item.name_zh || item.code
      }))
      // 去重：根据code去重，避免重复的国家选项
      .filter((item, index, self) => 
        index === self.findIndex(t => t.code === item.code)
      )
      .sort((a, b) => {
        // 按国家名称排序
        return a.name_zh.localeCompare(b.name_zh, 'zh-CN');
      });
    
    // 确保只有一个"全部区域"选项，添加到最前面
    filterCountries.value = [
      { code: '', name_zh: '全部区域' },
      ...countryOptions
    ];
  } catch (error) {
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
    // 确保至少有一个"全部区域"选项
    filterCountries.value = [{ code: '', name_zh: '全部区域' }];
  }
};

/**
 * 国家选择变化时的处理函数
 */
const handleCountryChange = () => {
  // 国家选择变化时不需要重新加载其他数据
  // 只需要在查询时使用新的国家筛选条件
  
  // 修复选中值显示
  nextTick(() => {
    setTimeout(() => {
      // 强制更新 el-select 状态，确保选中值正确显示
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100)
  })
};



/**
 * 日期范围变化时的处理函数
 * 
 * 当日期范围变化时：
 * - 重新加载有数据的客户列表（管理员）
 * - 重新加载产品列表（根据当前客户选择和新的日期范围）
 * - 重新加载国家列表（根据当前客户、产品和新的日期范围）
 * - 如果当前选择的产品在新日期范围内不存在，清空产品选择
 * - 如果当前选择的国家在新日期范围内不存在，清空国家选择
 */
const handleDateRangeChange = async () => {
  // 重新加载有数据的客户列表（管理员）
  if (isAdmin.value) {
    await fetchClientsWithData();
  }
  
  // 重新加载有数据的产品列表
  const clientId = searchForm.value.clientId || null;
  await fetchFilterProducts(clientId);
  
  // 如果当前选择的产品不在新列表中，清空产品选择
  if (searchForm.value.productId) {
    const productExists = filterProducts.value.some(p => p.value === searchForm.value.productId);
    if (!productExists) {
      searchForm.value.productId = '';
    }
  }
  
  // 重新加载有数据的国家列表
  const productId = searchForm.value.productId ? parseInt(searchForm.value.productId) : null;
  await fetchFilterCountries(clientId, productId);
  
  // 如果当前选择的国家不在新列表中，清空国家选择
  if (searchForm.value.countryCode) {
    const countryExists = filterCountries.value.some(c => c.code === searchForm.value.countryCode);
    if (!countryExists) {
      searchForm.value.countryCode = '';
    }
  }
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
    fetchAdData();
  }
};

// 重置筛选条件
const resetFilter = async () => {
  searchForm.value = {
    clientId: '',
    dateRange: [], // 重置日期范围，使用默认的当前月
    productId: '',
    countryCode: '' // 重置国家代码筛选
  };
  pagination.value.current = 1;
  // 重置排序
  sortInfo.value = {
    prop: 'date',
    order: 'descending'
  };
  
  // 重新加载有数据的客户列表（管理员）
  if (isAdmin.value) {
    await fetchClientsWithData();
  }
  
  // 重新加载有数据的产品列表（使用当前月的日期范围）
  // 客户用户不需要指定client_id，后端会自动根据当前用户过滤数据
  const defaultClientId = isAdmin.value ? null : null;
  await fetchFilterProducts(defaultClientId);
  
  fetchAdData(); // 重置后刷新数据
};

// 监听分页变化
let isInitializing = true;
let isChangingPageSize = false; // 标记是否正在改变每页条数

watch(
  () => [pagination.value.current, pagination.value.size],
  ([newCurrent, newSize], [oldCurrent, oldSize]) => {
    // 跳过初始化时的触发
    if (isInitializing) {
      return;
    }
    
    // 如果 oldCurrent 或 oldSize 是 undefined，说明是第一次触发，跳过
    if (oldCurrent === undefined || oldSize === undefined) {
      return;
    }
    
    // 如果正在改变每页条数，且页码被重置为1，这是预期的行为，直接刷新数据
    if (isChangingPageSize && newCurrent === 1 && newSize === oldSize) {
      isChangingPageSize = false;
      fetchAdData();
      return;
    }
    
    // 如果只是页码变化，直接刷新
    if (newCurrent !== oldCurrent && newSize === oldSize) {
      fetchAdData();
    }
    // 如果每页条数变化
    else if (newSize !== oldSize) {
      // 标记正在改变每页条数
      isChangingPageSize = true;
      // 如果页码不是第一页，重置到第一页（这会触发 watch 再次执行）
      if (newCurrent !== 1) {
        pagination.value.current = 1;
      } else {
        // 如果已经在第一页，直接刷新
        isChangingPageSize = false;
        fetchAdData();
      }
    }
  },
  { flush: 'post' }
);

// 编辑对话框状态
const editDialogVisible = ref(false);
const editFormRef = ref(null);
// 表单验证规则
const editRules = ref({
  product_id: [
  { required: true, message: '请选择产品', trigger: ['change', 'submit'] }
]
});

const editForm = ref({
  id: null,
  date: '',
  client_id: '',
  product_id: '',
  country_code: '',
  request_count: 0,
  match_count: 0,
  coverage_rate: 0,
  display_count: 0,
  display_rate: 0,
  click_count: 0,
  click_rate: 0,
  viewability_rate: 0,
  cpc: 0,
  pageviews: 0,
  ecpm_after_deduct: 0,
  ecpm_before_deduct: 0,
  revenue_after_deduct: 0,
  revenue_before_deduct: 0
});

// 客户ID变化时重新获取产品列表
watch(
  () => editForm.value.client_id,
  async (newVal, oldVal) => {
    // 只有在编辑模式下且客户ID真正变化时才清空产品ID
    // 避免在初始化编辑表单时清空产品ID
    if (newVal !== oldVal && oldVal !== null && oldVal !== undefined && oldVal !== '') {
      // 保存当前产品ID（如果存在）
      const currentProductId = editForm.value.product_id;
      
      if (newVal) {
        try {
          const clientProducts = await getProductsForSelect(newVal);
          products.value = clientProducts.map(item => ({
            value: item.value,
            label: item.label.replace(/^\d+\s*-\s*/, '')
          }));
          
          // 如果新列表中没有当前产品ID，则清空
          const productExists = products.value.some(p => p.value === currentProductId);
          if (!productExists) {
            editForm.value.product_id = null;
          }
        } catch (error) {
          if (!isErrorHandled(error)) {
            const errorMsg = extractErrorMessage(error);
            ElMessage.error(errorMsg);
          }
          products.value = [];
          editForm.value.product_id = null;
        }
      } else {
        products.value = [];
        editForm.value.product_id = null;
      }
    }
  }
);

// 修改数据（仅管理员）
const handleEdit = async (row) => {
  // 确保用户列表已加载（仅管理员需要）
  if (isAdmin.value && users.value.length === 0) {
    await fetchClientsWithData();
  }
  
  // 先设置基本信息，包括产品ID
  const currentProductId = row.product_id;
  
  // 加载产品列表（必须在使用前完成）
  if (row.client_id) {
    await fetchProducts(row.client_id);
    
    // 检查当前产品ID是否在产品列表中
    const productExists = products.value.some(p => p.value === currentProductId);
    if (!productExists && currentProductId) {
      // 如果产品不在列表中（可能已删除），尝试获取产品详情并添加到列表
      try {
        const productDetail = await getProductById(currentProductId);
        if (productDetail && productDetail.name) {
          products.value.push({
            value: currentProductId,
            label: productDetail.name
          });
        }
      } catch (error) {
        // 如果获取失败，至少保留产品ID，让用户知道需要选择新产品
        ElMessage.warning('原产品可能已不存在，请重新选择产品');
      }
    }
  }
  
  // 初始化编辑表单（确保产品列表已加载）
  editForm.value = {
    id: row.id,
    date: row.date,
    client_id: row.client_id,
    product_id: currentProductId, // 确保使用原始产品ID
    country_code: row.country_code || 'ZZ', // 国家代码，默认为 'ZZ'（全部区域）
    request_count: row.request_count,
    match_count: row.match_count,
    coverage_rate: row.coverage_rate || 0,
    display_count: row.display_count || 0,
    display_rate: row.display_rate || 0,
    click_count: row.click_count || 0,
    click_rate: row.click_rate || 0,
    viewability_rate: row.viewability_rate || 0,
    cpc: row.cpc || 0,
    pageviews: row.pageviews || 0,
    ecpm_after_deduct: row.ecpm_after_deduct || 0,
    ecpm_before_deduct: row.ecpm_before_deduct || 0,
    revenue_after_deduct: row.revenue_after_deduct || 0,
    revenue_before_deduct: row.revenue_before_deduct || 0
  };
  
  // 使用 nextTick 确保 DOM 更新后再打开对话框
  await nextTick();
  editDialogVisible.value = true;
};

// 产品选择变化处理
const handleProductChange = (value) => {
  editForm.value.product_id = value;
};

// 国家代码帮助提示
const handleCountryCodeHelp = () => {
  ElMessage.info({
    message: '支持的国家代码格式：\n1. 二字母代码：US、CN、JP\n2. 三字母代码：USA、CHN、JPN\n3. 数字代码：840、156、392\n4. 英文名称：United States of America、China、Japan\n5. 中文名称：美国、中国、日本',
    duration: 5000,
    showClose: true
  });
};

// 删除广告数据
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除日期为 ${row.date} 的广告数据吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
        appendTo: document.body, // 确保弹窗附加到 body，避免被对话框遮挡
        zIndex: 3001 // 确保 z-index 高于对话框
      }
    );
    
    // 确保CSRF令牌存在
    await ensureCsrfToken(() => fetchAdData());
    
    loading.value = true;
    await deleteAdData(row.id);
    ElMessage.success(getSuccessMessage('DATA_DELETE_SUCCESS'));
    await fetchAdData(); // 刷新数据列表
  } catch (error) {
    if (error !== 'cancel') {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
  } finally {
    loading.value = false;
  }
};

// 批量删除广告数据
const handleBatchDelete = async () => {
  if (selectedRows.value.length === 0) {
    ElMessage.warning(getWarningMessage('SELECT_DATA_TO_DELETE'));
    return;
  }
  
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedRows.value.length} 条广告数据吗？此操作不可恢复。`,
      '确认批量删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
        appendTo: document.body, // 确保弹窗附加到 body，避免被对话框遮挡
        zIndex: 3001 // 确保 z-index 高于对话框
      }
    );
    
    // 确保CSRF令牌存在
    await ensureCsrfToken(() => fetchAdData());
    
    loading.value = true;
    const dataIds = selectedRows.value.map(row => row.id);
    // batchDeleteAdData使用returnDataOnly: true，成功时直接返回数据，失败时抛出异常
    const response = await batchDeleteAdData(dataIds);
    
    // 如果执行到这里，说明操作成功（失败会抛出异常）
    const deletedCount = response?.deleted_count || selectedRows.value.length;
    ElMessage.success(getSuccessMessage('DATA_BATCH_DELETE_SUCCESS', deletedCount));
    selectedRows.value = []; // 清空选择
    await fetchAdData(); // 刷新数据列表
  } catch (error) {
    if (error !== 'cancel') {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
  } finally {
    loading.value = false;
  }
};

// 保存编辑
const saveEdit = async () => {
  try {
    // 确保CSRF令牌存在
    await ensureCsrfToken(() => fetchAdData());
    
    // 触发表单验证
    const formRef = editFormRef.value;
    if (!formRef) return;
    await formRef.validate();
    
    // 准备提交数据（只提交允许更新的字段）
    const payload = {
      id: editForm.value.id,
      product_id: editForm.value.product_id,
      country_code: editForm.value.country_code || 'ZZ', // 国家代码，如果为空则使用默认值 'ZZ'
      request_count: editForm.value.request_count,
      match_count: editForm.value.match_count,
      display_count: editForm.value.display_count,
      click_count: editForm.value.click_count,
      viewability_rate: editForm.value.viewability_rate,
      cpc: editForm.value.cpc,
      pageviews: editForm.value.pageviews,
      ecpm_after_deduct: editForm.value.ecpm_after_deduct,
      ecpm_before_deduct: editForm.value.ecpm_before_deduct,
      revenue_after_deduct: editForm.value.revenue_after_deduct,
      revenue_before_deduct: editForm.value.revenue_before_deduct
    };
    
    // 验证产品ID是否存在
    if (!payload.product_id) {
      ElMessage.error('请选择产品');
      return;
    }
    
    // 调用更新API
    const response = await updateAdData(payload);
    
    // updateAdData使用returnDataOnly: true，成功时直接返回数据，失败时抛出异常
    // 如果执行到这里，说明操作成功（失败会抛出异常）
    ElMessage.success(getSuccessMessage('DATA_UPDATE_SUCCESS'));
    editDialogVisible.value = false;
    fetchAdData(); // 刷新数据列表
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
  }
};

// 取消编辑
const cancelEdit = () => {
  editDialogVisible.value = false;
};

// 导出数据
const handleExport = async () => {
  try {
    // 对于客户用户，先检查是否有数据
    if (!isAdmin.value) {
      // 检查总数据量
      if (pagination.value.total === 0) {
        ElMessage.warning('当前没有可导出的数据，请先查询数据或导入数据');
        return;
      }
      
      // 如果当前列表为空但总数不为0，可能是筛选条件导致，仍然允许导出（让后端验证）
      // 但可以给用户一个提示
      if (adDataList.value.length === 0 && pagination.value.total > 0) {
        ElMessage.info('当前筛选条件下当前页无数据，将导出所有符合筛选条件的数据');
      }
    }
    
    const params = {};
    
    // 如果是管理员，可以选择指定客户ID，也可以不指定（导出所有客户的数据）
    if (isAdmin.value) {
      // 如果选择了客户，使用选择的客户ID
      if (searchForm.value.clientId) {
        params.client_id = parseInt(searchForm.value.clientId);
      }
      // 如果没有选择客户（全部客户），不传递client_id参数，后端会导出所有客户的数据
    }
    
    // 添加产品ID过滤
    if (searchForm.value.productId) {
      params.product_id = parseInt(searchForm.value.productId);
    }

    // 添加国家代码过滤
    if (searchForm.value.countryCode) {
      params.country_code = searchForm.value.countryCode;
    }

    // 添加日期范围过滤
    if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
      params.start_date = searchForm.value.dateRange[0];
      params.end_date = searchForm.value.dateRange[1];
    }
    
    // 排序参数由后端默认处理（按日期降序）

    await exportAdData(params);
    // 导出成功，显示提示信息
    ElMessage.success(getSuccessMessage('DATA_EXPORT_SUCCESS'));
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    
    // 如果是"无数据，不能导出"的错误，直接显示该消息
    if (errorMsg.includes('无数据') || errorMsg.includes('不能导出')) {
      ElMessage.warning(getWarningMessage('NO_DATA_TO_EXPORT'));
    } else {
      ElMessage.error(errorMsg);
    }
  }
};

// 选中的行
const selectedRows = ref([]);

// 选择项变更
const handleSelectionChange = (selection) => {
  selectedRows.value = selection;
};

// 加载页面数据的函数
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
    
    // 设置加载超时保护（20秒，避免过长等待）
    let timeoutId = null;
    const timeoutPromise = new Promise((_, reject) => {
      timeoutId = setTimeout(() => {
        reject(new Error('页面加载超时，请检查网络连接或刷新页面'));
      }, 20000);
    });
    
    // 优先加载广告数据（关键数据，用户最关心）
    const criticalPromises = [
      fetchAdData().catch(error => {
        if (error.response?.status === 401) {
          return;
        }
        // 静默处理错误
      })
    ];
    
    // 先等待关键数据加载完成
    try {
      await Promise.race([
        Promise.allSettled(criticalPromises),
        timeoutPromise
      ]);
    } finally {
      // 清理超时定时器
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    }
    
    // 然后并行加载非关键数据（客户列表、产品列表等）
    // 这些数据可以延迟加载，不影响用户查看主要数据
    const nonCriticalPromises = [];
    
    // 加载有数据的客户列表（管理员）
    if (isAdmin.value) {
      nonCriticalPromises.push(
        fetchClientsWithData().catch(error => {
          if (error.response?.status === 401) {
            return;
          }
          // 静默处理错误
        })
      );
    }
    
    // 根据用户角色加载产品列表
    let defaultClientId = null;
    
    // 加载编辑对话框的产品列表（用于编辑功能，可以延迟）
    nonCriticalPromises.push(
      fetchProducts(defaultClientId).catch(error => {
        if (error.response?.status === 401) {
          return;
        }
        // 静默处理错误
      })
    );
    
    // 加载筛选表单的产品列表（只显示有数据的产品，使用当前月的日期范围）
    nonCriticalPromises.push(
      fetchFilterProducts(defaultClientId).catch(error => {
        if (error.response?.status === 401) {
          return;
        }
        // 静默处理错误
      })
    );
    
    // 加载筛选表单的国家列表（只显示有数据的国家，使用当前月的日期范围）
    nonCriticalPromises.push(
      fetchFilterCountries(defaultClientId, null).catch(error => {
        if (error.response?.status === 401) {
          return;
        }
        // 静默处理错误
      })
    );
    
    // 非关键数据异步加载，不阻塞页面显示
    Promise.allSettled(nonCriticalPromises).catch(() => {
      // 静默处理错误，不影响用户体验
    });
  } catch (error) {
    // 超时或其他错误
    if (error.message && error.message.includes('超时')) {
      ElMessage.error(error.message);
      // 超时后停止loading
      loading.value = false;
    } else if (error.response?.status === 401) {
      // 401错误已在拦截器中处理，这里不需要额外处理
      loading.value = false;
    } else {
      // 其他错误
      if (!isErrorHandled(error)) {
        const errorMsg = extractErrorMessage(error);
        ElMessage.error(`页面初始化失败: ${errorMsg}`);
      }
      loading.value = false;
    }
  }
};

// 标记是否已经初始化
let isPageInitialized = false;

// 页面挂载时加载数据
let mountedTimeoutId = null;
onMounted(async () => {
  // 路由守卫已经处理了认证检查，这里不需要重复检查
  // 延迟加载数据，让页面先渲染出来
  await nextTick();
  
  // 加载列显示设置
  loadColumnVisibility();
  
  mountedTimeoutId = setTimeout(async () => {
    await loadPageData();
    // 初始化完成后，启用分页 watch
    await nextTick();
    isInitializing = false;
    isPageInitialized = true;
    mountedTimeoutId = null;
  }, 0);
});

// 组件卸载时清理定时器
onUnmounted(() => {
  if (mountedTimeoutId) {
    clearTimeout(mountedTimeoutId);
    mountedTimeoutId = null;
  }
  if (fetchAdDataTimer) {
    clearTimeout(fetchAdDataTimer);
    fetchAdDataTimer = null;
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
  
  // 加载该客户的产品列表
  loadClientProducts(selectedClientId.value);
  
  // 显示产品管理对话框
  productManagementVisible.value = true;
};

// 加载客户产品列表
const loadClientProducts = async (clientId) => {
  if (!clientId) {
    selectedClientProducts.value = [];
    return;
  }
  
  loadingProducts.value = true;
  try {
    const result = await getProductsWithData(clientId);
    selectedClientProducts.value = result.data || [];
  } catch (error) {
    if (!isErrorHandled(error)) {
      ElMessage.error(extractErrorMessage(error));
    }
    selectedClientProducts.value = [];
  } finally {
    loadingProducts.value = false;
  }
};

// 处理产品管理刷新事件
const handleProductManagementRefresh = () => {
  // 产品管理对话框关闭时刷新数据
  fetchAdData();
};

// 监听路由变化，当从其他页面导航到 AdData 时自动刷新数据
watch(
  () => route.path,
  (newPath, oldPath) => {
    // 当路由路径是 /app/ad-data 且不是首次加载时，刷新数据
    // 确保是从其他页面导航过来的，而不是首次加载
    if (newPath === '/app/ad-data' && isPageInitialized && oldPath && oldPath !== '/app/ad-data') {
      // 重置分页到第一页
      pagination.value.current = 1;
      // 刷新数据
      loadPageData();
    }
  },
  { immediate: false }
);

</script>

<style scoped>
.ad-data-container {
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
  margin-right: var(--spacing-md);
}

/* 桌面端筛选表单优化 - 响应式列布局 */
@media (min-width: 1200px) {
  .filter-form :deep(.el-form-item) {
    width: 280px;
  }
}

@media (min-width: 1400px) {
  .filter-form :deep(.el-form-item) {
    width: 300px;
  }
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
  background-color: #ecf5ff;
  border: 1px solid #b3d8ff;
  border-radius: var(--radius-md, 4px);
  color: #409eff;
  font-size: var(--font-size-sm, 14px);
}

.filter-hint .el-icon {
  color: #409eff;
  font-size: var(--font-size-base, 16px);
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

.edit-form {
  padding: var(--spacing-md) 0;
}

.edit-form :deep(.el-form-item) {
  margin-bottom: var(--spacing-lg);
}

.edit-form :deep(.el-form-item__label) {
  white-space: nowrap;
  line-height: 32px;
  text-align: right;
  padding-right: var(--spacing-md);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

/* 对话框footer按钮优化 */
.dialog-footer {
  display: flex;
  justify-content: center;
  gap: 12px;
  width: 100%;
}

.dialog-footer .el-button {
  min-width: 90px;
  padding: 8px 20px;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .ad-data-container {
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
  
  /* 筛选表单移动端优化 - 强制覆盖 inline 表单样式 */
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
    max-width: 100% !important;
  }
  
  .filter-form :deep(.el-date-editor .el-input__wrapper) {
    width: 100% !important;
  }
  
  .filter-form :deep(.el-date-editor .el-range-separator) {
    width: auto !important;
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
  }
  
  .filter-form :deep(.el-form-item:last-child .el-button) {
    flex: 1;
    min-height: var(--touch-target-size);
    width: auto;
    white-space: nowrap;
  }
  
  .filter-hint {
    margin-top: var(--spacing-sm);
    padding: var(--spacing-sm);
    font-size: var(--font-size-xs);
    line-height: 1.5;
  }
  
  .data-table-card {
    margin-bottom: var(--spacing-md);
  }
  
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
  
  .el-table :deep(.el-table-column--selection) {
    width: 50px !important;
  }
  
  .pagination-container {
    margin-top: var(--spacing-md);
    padding: var(--spacing-md) 0;
    text-align: center;
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
  
  /* 移动端对话框优化 */
  .el-dialog {
    width: 95% !important;
    margin: var(--spacing-md) auto !important;
  }
  
  .el-dialog :deep(.el-dialog__body) {
    padding: var(--spacing-md);
  }
  
  .edit-form :deep(.el-form-item__label) {
    width: 100px !important;
    text-align: left;
  }
  
  /* 移动端表格操作按钮优化 */
  .el-table :deep(.el-table-column--action) {
    width: 120px !important;
  }
  
  .el-table :deep(.el-table-column--action .el-button) {
    padding: 4px 8px;
    font-size: var(--font-size-xs);
    min-width: 50px;
    min-height: 32px;
  }
}

/* ====== 平板端优化 (768px - 1024px) ====== */
@media (min-width: 768px) and (max-width: 1024px) {
  .ad-data-container {
    padding: var(--spacing-lg);
  }
  
  .page-header {
    padding: var(--spacing-lg);
    margin-bottom: var(--spacing-lg);
  }
  
  .action-buttons {
    gap: var(--spacing-md);
  }
  
  .action-buttons .el-button {
    min-height: 40px;
  }
  
  .filter-card {
    margin-bottom: var(--spacing-lg);
  }
  
  .filter-card :deep(.el-card__body) {
    padding: var(--spacing-lg);
  }
  
  /* 平板端筛选表单优化 - 两列布局 */
  .filter-form :deep(.el-form-item) {
    width: calc(50% - var(--spacing-md));
    margin-right: var(--spacing-md);
    margin-bottom: var(--spacing-md);
  }
  
  .filter-form :deep(.el-form-item:nth-child(2n)) {
    margin-right: 0;
  }
  
  .filter-form :deep(.el-form-item:last-child) {
    width: 100%;
    margin-right: 0;
    margin-top: var(--spacing-sm);
  }
  
  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-lg);
  }
  
  /* 平板端表格优化 */
  .el-table {
    font-size: var(--font-size-sm);
  }
  
  .el-table :deep(.el-table__cell) {
    padding: var(--spacing-sm);
  }
  
  .el-table :deep(.el-table__header th),
  .el-table :deep(.el-table__body td) {
    font-size: var(--font-size-sm);
    padding: var(--spacing-sm);
  }
  
  /* 平板端分页优化 */
  .pagination-container {
    padding: var(--spacing-md) 0;
  }
  
  .pagination-component :deep(.el-pagination__total) {
    font-size: var(--font-size-sm);
  }
  
  .pagination-component :deep(.btn-prev),
  .pagination-component :deep(.btn-next),
  .pagination-component :deep(.el-pager li) {
    min-width: 36px;
    min-height: 36px;
    font-size: var(--font-size-sm);
  }
  
  /* 平板端对话框优化 */
  .el-dialog {
    width: 85% !important;
    max-width: 700px;
  }
  
  .el-dialog :deep(.el-dialog__body) {
    padding: var(--spacing-lg);
  }
}

/* ====== 小屏手机优化 (< 480px) ====== */
@media (max-width: 480px) {
  .ad-data-container {
    padding: var(--spacing-sm);
  }
  
  .page-header {
    padding: var(--spacing-sm);
    margin-bottom: var(--spacing-sm);
  }
  
  .action-buttons .el-button {
    font-size: var(--font-size-sm);
    padding: var(--spacing-sm) var(--spacing-md);
  }
  
  .filter-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
  }
  
  .filter-form :deep(.el-form-item) {
    margin-bottom: var(--spacing-sm) !important;
  }
  
  .filter-hint {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs);
    line-height: 1.4;
  }
  
  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-xs);
  }
  
  /* 小屏手机表格进一步优化 */
  .el-table {
    font-size: var(--font-size-xs);
    min-width: 700px; /* 小屏手机表格最小宽度稍小 */
  }
  
  .el-table :deep(.el-table__cell) {
    padding: var(--spacing-xs);
  }
  
  .el-table :deep(.el-table__header th),
  .el-table :deep(.el-table__body td) {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs);
    line-height: 1.3;
  }
  
  .el-table :deep(.el-table-column--selection) {
    width: 40px !important;
  }
  
  /* 小屏手机操作按钮进一步优化 */
  .el-table :deep(.el-table-column--action) {
    width: 100px !important;
  }
  
  .el-table :deep(.el-table-column--action .el-button) {
    padding: 2px 6px;
    font-size: var(--font-size-xs);
    min-width: 45px;
    min-height: 28px;
  }
  
  .pagination-container {
    padding: var(--spacing-sm) 0;
  }
  
  .pagination-component {
    font-size: var(--font-size-xs);
  }
  
  .pagination-component :deep(.el-pagination__total) {
    font-size: var(--font-size-xs);
    margin-right: var(--spacing-xs);
  }
  
  .pagination-component :deep(.btn-prev),
  .pagination-component :deep(.btn-next),
  .pagination-component :deep(.el-pager li) {
    min-width: 32px;
    min-height: 32px;
    font-size: var(--font-size-xs);
    padding: 0 4px;
  }
  
  /* 小屏手机对话框优化 */
  .el-dialog {
    width: 98% !important;
    margin: var(--spacing-sm) auto !important;
  }
  
  .el-dialog :deep(.el-dialog__body) {
    padding: var(--spacing-sm);
  }
  
  .edit-form :deep(.el-form-item__label) {
    width: 80px !important;
    font-size: var(--font-size-xs);
  }
  
  .edit-form :deep(.el-form-item__content) {
    font-size: var(--font-size-sm);
  }
  
  .dialog-footer .el-button {
    min-width: 80px;
    padding: 6px 16px;
    font-size: var(--font-size-sm);
  }
}

/* ====== 横屏模式优化 (移动设备横屏) ====== */
@media (max-width: 1024px) and (orientation: landscape) {
  .ad-data-container {
    padding: var(--spacing-md);
  }
  
  .page-header {
    flex-direction: row;
    align-items: center;
  }
  
  .action-buttons {
    flex-direction: row;
    width: auto;
  }
  
  .action-buttons .el-button {
    width: auto;
    min-width: 120px;
  }
  
  /* 横屏时筛选表单可以两列布局 */
  .filter-form :deep(.el-form-item) {
    width: calc(50% - var(--spacing-sm));
    margin-right: var(--spacing-sm);
  }
  
  .filter-form :deep(.el-form-item:nth-child(2n)) {
    margin-right: 0;
  }
  
  .filter-form :deep(.el-form-item:last-child) {
    width: 100%;
    margin-right: 0;
  }
  
  /* 横屏时表格可以显示更多列 */
  .el-table {
    min-width: 900px;
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