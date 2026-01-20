<template>
  <div class="ad-data-container">
    <div class="page-header">
      <div class="action-buttons">
        <el-upload
          v-if="isAdmin"
          class="upload-demo"
          :show-file-list="false"
          :http-request="handleImport"
          accept=".xlsx,.xls"
          :disabled="loading"
        >
          <el-button type="primary" :icon="Upload" :loading="importing" :disabled="loading">导入Excel</el-button>
        </el-upload>
        <el-button 
          v-if="isAdmin && selectedRows.length > 0" 
          type="danger" 
          @click="handleBatchDelete" 
          :icon="Delete"
          :disabled="loading"
        >
          批量删除 ({{ selectedRows.length }})
        </el-button>
      </div>
    </div>

    <!-- 筛选控件 -->
    <el-card class="filter-card">
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="日期范围">
          <el-date-picker
            v-model="searchForm.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            @change="handleDateRangeChange"
          ></el-date-picker>
        </el-form-item>
        <el-form-item v-if="isAdmin" label="客户">
          <el-select 
            v-model="searchForm.clientId" 
            placeholder="全部客户" 
            clearable
            @change="handleClientChange"
          >
            <el-option v-for="user in users" :key="user.value" :label="user.label" :value="user.value"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="产品">
          <el-select 
            v-model="searchForm.productId" 
            placeholder="全部产品" 
            clearable
            @change="handleProductChange"
          >
            <el-option v-for="product in products" :key="product.value" :label="product.label" :value="product.value"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="国家">
          <el-select 
            v-model="searchForm.countryCode" 
            placeholder="全部区域" 
            clearable
            @change="fetchData"
            style="width: 100%;"
          >
            <el-option v-for="country in countries" :key="country.code" :label="country.name_zh" :value="country.code"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchData" :loading="loading">查询</el-button>
          <el-button @click="resetFilter" :disabled="loading">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="data-table-card">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-weight: 600; font-size: 16px;">TB搜索数据</span>
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
        :data="tableData"
        border
        stripe
        style="width: 100%"
        @selection-change="handleSelectionChange"
        @sort-change="handleSortChange"
        :summary-method="getSummaries"
        show-summary
      >
        <el-table-column type="selection" width="55"></el-table-column>
        <el-table-column v-if="columnVisibility.date" prop="date" label="DATE" sortable="custom" width="120"></el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.user_name" prop="user_name" label="所属客户" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.product_name" prop="product_name" label="SUBID" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.country_name_zh" prop="country_name_zh" label="GEO" width="120">
          <template #default="{ row }">
            {{ row.country_code }} ({{ row.country_name_zh }})
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.redirects" prop="redirects" label="REDIRECTS" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.searches" prop="searches" label="SEARCHES" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.monetized" prop="monetized" label="MONETIZED" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.clicks" prop="clicks" label="CLICKS" sortable="custom"></el-table-column>
        
        <el-table-column v-if="columnVisibility.revenue" prop="revenue" :label="isAdmin ? 'REVENUE(扣)' : 'REVENUE'" sortable="custom">
          <template #default="{ row }">
            {{ formatCurrency(row.revenue) }}
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.revenue_before_deduct" prop="revenue_before_deduct" label="REVENUE" sortable="custom">
          <template #default="{ row }">
            {{ formatCurrency(row.revenue_before_deduct) }}
          </template>
        </el-table-column>

        <el-table-column v-if="columnVisibility.rpm" prop="rpm" :label="isAdmin ? 'RPM(扣)' : 'RPM'" sortable="custom">
          <template #default="{ row }">
            {{ formatCurrency(row.rpm) }}
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.rpm_before_deduct" prop="rpm_before_deduct" label="RPM" sortable="custom">
          <template #default="{ row }">
            {{ formatCurrency(row.rpm_before_deduct) }}
          </template>
        </el-table-column>

        <el-table-column v-if="isAdmin" label="操作" width="150" fixed="right">
          <template #default="scope">
            <el-button size="small" type="primary" @click="handleEdit(scope.row)">修改</el-button>
            <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.size"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        ></el-pagination>
      </div>
    </el-card>

    <!-- 编辑对话框 -->
    <el-dialog 
      v-model="editDialogVisible" 
      title="修改数据" 
      width="500px"
      :append-to-body="true"
    >
      <el-form :model="editForm" label-width="120px">
        <el-form-item label="REDIRECTS">
          <el-input v-model.number="editForm.redirects" type="number"></el-input>
        </el-form-item>
        <el-form-item label="SEARCHES">
          <el-input v-model.number="editForm.searches" type="number"></el-input>
        </el-form-item>
        <el-form-item label="MONETIZED">
          <el-input v-model.number="editForm.monetized" type="number"></el-input>
        </el-form-item>
        <el-form-item label="CLICKS">
          <el-input v-model.number="editForm.clicks" type="number"></el-input>
        </el-form-item>
        <el-form-item label="REVENUE(扣)">
          <el-input v-model.number="editForm.revenue" type="number" step="0.01"></el-input>
        </el-form-item>
        <el-form-item label="REVENUE">
          <el-input v-model.number="editForm.revenue_before_deduct" type="number" step="0.01"></el-input>
        </el-form-item>
        <el-form-item label="RPM(扣)">
          <el-input v-model.number="editForm.rpm" type="number" step="0.01"></el-input>
        </el-form-item>
        <el-form-item label="RPM">
          <el-input v-model.number="editForm.rpm_before_deduct" type="number" step="0.01"></el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="date" :disabled="true">DATE（固定显示）</el-checkbox>
        <el-checkbox v-if="isAdmin" label="user_name">所属客户</el-checkbox>
        <el-checkbox label="product_name" :disabled="true">SUBID（固定显示）</el-checkbox>
        <el-checkbox label="country_name_zh">GEO</el-checkbox>
        <el-checkbox label="redirects">REDIRECTS</el-checkbox>
        <el-checkbox label="searches">SEARCHES</el-checkbox>
        <el-checkbox label="monetized">MONETIZED</el-checkbox>
        <el-checkbox label="clicks">CLICKS</el-checkbox>
        <el-checkbox label="revenue">REVENUE(扣)</el-checkbox>
        <el-checkbox v-if="isAdmin" label="revenue_before_deduct">REVENUE</el-checkbox>
        <el-checkbox label="rpm">RPM(扣)</el-checkbox>
        <el-checkbox v-if="isAdmin" label="rpm_before_deduct">RPM</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, nextTick } from 'vue';
import { useAuthStore } from '../../store';
import { ElMessage, ElMessageBox, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus';
import { Upload, Delete, Setting } from '@element-plus/icons-vue';
import { getTBSearchDataList, updateTBSearchData, deleteTBSearchData, batchDeleteTBSearchData, importTBSearchData, getClientsWithTBSearchData, getProductsWithTBSearchData, getCountriesWithTBSearchData } from '../../api/tbSearchData';
import { extractErrorMessage, isErrorHandled, ensureCsrfToken } from '../../utils/api';

const authStore = useAuthStore();
const isAdmin = computed(() => authStore.isAdmin);

const loading = ref(false);
const importing = ref(false);
const tableData = ref([]);
const columnSettingVisible = ref(false);
const users = ref([]);
const products = ref([]);
const countries = ref([]);
const selectedRows = ref([]);

const pagination = ref({
  current: 1,
  size: 10,
  total: 0
});

const searchForm = ref({
  dateRange: [],
  clientId: '',
  productId: '',
  countryCode: ''
});

// 列显示状态（默认全部显示）
const getDefaultColumnVisibility = () => ({
  date: true,  // 固定显示
  user_name: isAdmin.value,
  product_name: true,  // 固定显示
  country_name_zh: true,
  redirects: true,
  searches: true,
  monetized: true,
  clicks: true,
  revenue: true,
  revenue_before_deduct: isAdmin.value,
  rpm: true,
  rpm_before_deduct: isAdmin.value
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
    const saved = localStorage.getItem('tbSearchData_columnVisibility');
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
      redirects: columnVisibility.redirects,
      searches: columnVisibility.searches,
      monetized: columnVisibility.monetized,
      clicks: columnVisibility.clicks,
      revenue: columnVisibility.revenue,
      revenue_before_deduct: columnVisibility.revenue_before_deduct,
      rpm: columnVisibility.rpm,
      rpm_before_deduct: columnVisibility.rpm_before_deduct
    };
    localStorage.setItem('tbSearchData_columnVisibility', JSON.stringify(toSave));
    columnSettingVisible.value = false;
    ElMessage.success('列显示设置已保存');
  } catch (error) {
    console.error('保存列显示设置失败:', error);
    ElMessage.error('保存设置失败');
  }
};

const sortInfo = ref({
  prop: 'date',
  order: 'descending'
});

const editDialogVisible = ref(false);
const editForm = ref({});

onMounted(async () => {
  // 加载列显示设置
  loadColumnVisibility();
  await loadFilterOptions();
  fetchData();
});

// 获取当前日期范围（用于筛选条件）
const getDateRange = () => {
  let startDate = null;
  let endDate = null;
  if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
    startDate = searchForm.value.dateRange[0];
    endDate = searchForm.value.dateRange[1];
  }
  return { startDate, endDate };
};

// 加载所有筛选条件
const loadFilterOptions = async () => {
  const { startDate, endDate } = getDateRange();
  
  if (isAdmin.value) {
    await loadUsers(startDate, endDate);
  }
  await loadProducts(searchForm.value.clientId || null, startDate, endDate);
  await loadCountries(searchForm.value.clientId || null, searchForm.value.productId || null, startDate, endDate);
};

const loadUsers = async (startDate = null, endDate = null) => {
  try {
    const result = await getClientsWithTBSearchData(startDate, endDate);
    const data = result.data || [];
    
    users.value = [
      { label: '全部客户', value: '' },
      ...data.map(item => ({
        value: item.id,
        label: item.full_name || '未知客户'
      }))
    ];
  } catch (error) {
    if (!isErrorHandled(error)) {
      // 错误已通过 isErrorHandled 处理
    }
    users.value = [{ label: '全部客户', value: '' }];
  }
};

const loadProducts = async (clientId = null, startDate = null, endDate = null) => {
  try {
    const result = await getProductsWithTBSearchData(clientId, startDate, endDate);
    const data = result.data || [];
    
    products.value = [
      { label: '全部产品', value: '' },
      ...data.map(item => ({
        value: String(item.id),
        label: item.name || '未知产品'
      }))
    ];
  } catch (error) {
    if (!isErrorHandled(error)) {
      // 错误已通过 isErrorHandled 处理
    }
    products.value = [{ label: '全部产品', value: '' }];
  }
};

const loadCountries = async (clientId = null, productId = null, startDate = null, endDate = null) => {
  try {
    const result = await getCountriesWithTBSearchData(clientId, productId, startDate, endDate);
    const data = result.data || [];
    
    countries.value = [
      { code: '', name_zh: '全部区域' },
      ...data.map(item => ({
        code: item.code,
        name_zh: item.name_zh || item.code
      }))
    ];
  } catch (error) {
    if (!isErrorHandled(error)) {
      // 错误已通过 isErrorHandled 处理
    }
    countries.value = [{ code: '', name_zh: '全部区域' }];
  }
};

// 日期范围变化时的处理
const handleDateRangeChange = async () => {
  // 重新加载所有筛选条件（基于新的日期范围）
  await loadFilterOptions();
  // 如果当前选择的产品或国家不在新列表中，清空选择
  if (searchForm.value.productId) {
    const productExists = products.value.some(p => p.value === searchForm.value.productId);
    if (!productExists) {
      searchForm.value.productId = '';
    }
  }
  if (searchForm.value.countryCode) {
    const countryExists = countries.value.some(c => c.code === searchForm.value.countryCode);
    if (!countryExists) {
      searchForm.value.countryCode = '';
    }
  }
  // 重置分页并获取数据
  pagination.value.current = 1;
  fetchData();
};

const handleClientChange = async (val) => {
  const { startDate, endDate } = getDateRange();
  await loadProducts(val || null, startDate, endDate);
  await loadCountries(val || null, null, startDate, endDate);
  // 如果当前选择的产品不在新列表中，清空产品选择
  if (searchForm.value.productId) {
    const productExists = products.value.some(p => p.value === searchForm.value.productId);
    if (!productExists) {
      searchForm.value.productId = '';
    }
  }
  // 清空国家选择，因为产品变化了
  searchForm.value.countryCode = '';
  pagination.value.current = 1;
  
  // 修复选中值显示
  nextTick(() => {
    setTimeout(() => {
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100);
  });
  
  fetchData();
};

// 产品选择变化时的处理
const handleProductChange = async () => {
  const { startDate, endDate } = getDateRange();
  await loadCountries(searchForm.value.clientId || null, searchForm.value.productId || null, startDate, endDate);
  // 如果当前选择的国家不在新列表中，清空国家选择
  if (searchForm.value.countryCode) {
    const countryExists = countries.value.some(c => c.code === searchForm.value.countryCode);
    if (!countryExists) {
      searchForm.value.countryCode = '';
    }
  }
  pagination.value.current = 1;
  
  // 修复选中值显示
  nextTick(() => {
    setTimeout(() => {
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100);
  });
  
  fetchData();
};

// 分页处理
const handleSizeChange = (size) => {
  pagination.value.size = size;
  pagination.value.current = 1;  // 分页大小变化时重置到第一页
  fetchData();
};

const handlePageChange = (page) => {
  pagination.value.current = page;
  fetchData();
};

const fetchData = async () => {
  loading.value = true;
  try {
    const params = {
      page: pagination.value.current,
      page_size: pagination.value.size,
      sort_by: sortInfo.value.prop,
      sort_order: sortInfo.value.order === 'ascending' ? 'asc' : 'desc'
    };
    
    // 如果选择了日期范围，使用选择的日期范围
    // 如果没有选择日期范围，后端默认使用当前月的数据
    if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
      params.start_date = searchForm.value.dateRange[0];
      params.end_date = searchForm.value.dateRange[1];
    }
    // 如果没有选择日期范围，不传递日期参数，让后端使用默认的当前月
    
    if (searchForm.value.clientId) params.client_id = searchForm.value.clientId;
    if (searchForm.value.productId) params.product_id = searchForm.value.productId;
    if (searchForm.value.countryCode) params.country_code = searchForm.value.countryCode;

    const res = await getTBSearchDataList(params);
    
    // res已经是标准分页格式，直接使用data和total字段
    // getTBSearchDataList使用paginated: true，失败时会抛出异常
    tableData.value = res.data || [];
    // 确保total是数字类型
    const totalValue = typeof res.total === 'number' ? res.total : parseInt(res.total || 0, 10);
    pagination.value.total = totalValue;
    
    // 如果查询结果为空，且没有选择任何筛选条件，提示用户
    if (tableData.value.length === 0 && pagination.value.total === 0 && 
        !searchForm.value.dateRange && !searchForm.value.clientId && 
        !searchForm.value.productId && !searchForm.value.countryCode) {
      // 已经在使用大日期范围，如果还是没有数据，说明确实没有数据
    }
  } catch (error) {
    if (!isErrorHandled(error)) {
      ElMessage.error(extractErrorMessage(error));
    }
  } finally {
    loading.value = false;
  }
};

const handleSortChange = ({ prop, order }) => {
  sortInfo.value = { prop, order };
  fetchData();
};

const handleSelectionChange = (val) => {
  selectedRows.value = val;
};

const resetFilter = async () => {
  searchForm.value = {
    dateRange: [],
    clientId: '',
    productId: '',
    countryCode: ''
  };
  pagination.value.current = 1;
  await loadFilterOptions();
  fetchData();
};

const formatCurrency = (val) => {
  return val ? `$${Number(val).toFixed(2)}` : '$0.00';
};

const getSummaries = (param) => {
  const { columns, data } = param;
  const sums = [];
  
  // 确保 data 是数组
  if (!Array.isArray(data)) {
    return columns.map(() => '');
  }
  
  columns.forEach((column, index) => {
    if (index === 0) {
      sums[index] = '合计';
      return;
    }
    const prop = column.property;
    if (['redirects', 'searches', 'monetized', 'clicks', 'revenue', 'revenue_before_deduct', 'rpm', 'rpm_before_deduct'].includes(prop)) {
      const values = data.map(item => {
        const value = item?.[prop];
        return value !== null && value !== undefined ? Number(value) : 0;
      }).filter(val => !Number.isNaN(val));
      
      if (values.length > 0) {
        const sum = values.reduce((prev, curr) => prev + curr, 0);
        sums[index] = ['revenue', 'revenue_before_deduct', 'rpm', 'rpm_before_deduct'].includes(prop) ? formatCurrency(sum) : sum;
      } else {
        sums[index] = '';
      }
    } else {
      sums[index] = '';
    }
  });
  return sums;
};

const handleImport = async (options) => {
  const { file } = options;
  const formData = new FormData();
  formData.append('file', file);
  
  importing.value = true;
  try {
    const res = await importTBSearchData(formData);
    // 优先显示 data.message（后端业务消息），其次显示外层 message，最后是默认消息
    const msg = res.data?.message || res.message || '导入成功';
    ElMessage.success(msg);
    
    // 如果有部分错误，也显示出来
    if (res.data?.errors && res.data.errors.length > 0) {
      setTimeout(() => {
        const errorMsg = `部分数据导入失败（${res.data.errors.length}条）：\n` + res.data.errors.join('\n');
        ElMessage.warning({
          message: errorMsg,
          duration: 10000,
          showClose: true,
          dangerouslyUseHTMLString: true,
          formatter: (msg) => msg.replace(/\n/g, '<br/>')
        });
      }, 500);
    }
    
    // 导入成功后，重新加载筛选条件并刷新数据，确保能看到新导入的数据
    // 重置到第一页
    pagination.value.current = 1;
    
    // 如果用户没有选择日期范围，后端默认只显示当前月的数据
    // 为了确保能看到新导入的数据，如果当前没有选择日期范围，清除客户筛选
    // 这样至少能看到"默认客户（导入数据）"的数据
    if (!searchForm.value.dateRange || searchForm.value.dateRange.length === 0) {
      // 没有选择日期范围时，清除客户筛选，确保能看到所有客户的数据（包括默认客户）
      if (isAdmin.value) {
        searchForm.value.clientId = '';
      }
    }
    
    // 重新加载筛选条件（基于当前日期范围）
    await loadFilterOptions();
    
    // 刷新数据
    await fetchData();
    
    // 如果导入成功但数据没有显示，提示用户调整筛选条件
    if (res.data?.message && res.data.message.includes('成功导入')) {
      setTimeout(() => {
        if (tableData.value.length === 0 && pagination.value.total === 0) {
          ElMessage.info({
            message: '导入成功！如果看不到数据，请检查日期范围筛选条件是否包含导入数据的日期。',
            duration: 5000,
            showClose: true
          });
        }
      }, 1000);
    }
  } catch (error) {
    if (!isErrorHandled(error)) {
      ElMessage.error(extractErrorMessage(error));
    }
  } finally {
    importing.value = false;
  }
};

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确认删除该条数据?', '警告', { type: 'warning' });
    await deleteTBSearchData(row.id);
    ElMessage.success('删除成功');
    fetchData();
  } catch (e) {
    if (e !== 'cancel') {
      // 错误已处理
    }
  }
};

const handleBatchDelete = async () => {
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedRows.value.length} 条数据?`, '警告', { type: 'warning' });
    await batchDeleteTBSearchData(selectedRows.value.map(r => r.id));
    ElMessage.success('批量删除成功');
    selectedRows.value = [];
    fetchData();
  } catch (e) {
    if (e !== 'cancel') {
      // 错误已处理
    }
  }
};

const handleEdit = (row) => {
  editForm.value = { ...row };
  editDialogVisible.value = true;
};

const saveEdit = async () => {
  try {
    await updateTBSearchData(editForm.value);
    ElMessage.success('修改成功');
    editDialogVisible.value = false;
    fetchData();
  } catch (error) {
    // 错误已处理
  }
};
</script>

<style scoped>
.ad-data-container {
  padding: 20px;
}
.page-header {
  margin-bottom: 20px;
}
.filter-card {
  margin-bottom: 20px;
}

/* 筛选表单样式优化 */
.filter-form {
  margin-bottom: 0;
}

.filter-form :deep(.el-form-item) {
  width: 300px;
  margin-bottom: 16px;
  margin-right: 16px;
  vertical-align: top;
  display: inline-flex;
  align-items: center;
}

/* 确保标签宽度一致 */
.filter-form :deep(.el-form-item__label) {
  width: auto;
  min-width: 60px;
  text-align: right;
  padding-right: 12px;
  line-height: 32px;
}

/* 确保内容区域对齐 */
.filter-form :deep(.el-form-item__content) {
  flex: 1;
  line-height: 32px;
}

/* 确保所有输入框和选择框宽度一致 */
.filter-form :deep(.el-input),
.filter-form :deep(.el-select),
.filter-form :deep(.el-date-editor) {
  width: 100%;
}

/* 确保输入框和选择框的高度一致 */
.filter-form :deep(.el-input__wrapper),
.filter-form :deep(.el-select .el-input__wrapper) {
  height: 32px;
  min-height: 32px;
}

/* 下拉框宽度优化 */
.filter-form :deep(.el-select) {
  min-width: 100%;
}

/* 日期选择器宽度优化 */
.filter-form :deep(.el-date-editor) {
  width: 100%;
}

/* 确保输入框内部元素对齐 */
.filter-form :deep(.el-input__inner) {
  height: 100%;
  line-height: 1;
}

/* 按钮组不限制宽度 */
.filter-form :deep(.el-form-item:last-child) {
  width: auto;
  margin-right: 0;
}

/* 响应式优化 */
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

/* 移动端优化 */
@media (max-width: 767px) {
  .filter-form :deep(.el-form-item) {
    width: 100% !important;
    margin-right: 0 !important;
  }
  
  .filter-form :deep(.el-input),
  .filter-form :deep(.el-select),
  .filter-form :deep(.el-date-editor) {
    width: 100% !important;
  }
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
