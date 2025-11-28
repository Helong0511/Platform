<template>
  <el-dialog 
    v-model="visible" 
    :width="isMobile ? '95%' : (isTablet ? '90%' : '1400px')"
    :close-on-click-modal="false"
    @close="handleClose"
    class="product-management-dialog"
    :show-close="true"
    align-center
    :center="true"
  >
    <template #header>
      <div class="dialog-header">
        <div class="header-content">
          <div class="header-left">
            <el-icon class="header-icon"><Box /></el-icon>
            <div class="header-text">
              <h4 class="header-title">{{ clientName }}</h4>
              <p class="header-subtitle">产品管理</p>
            </div>
          </div>
          <div class="header-right">
            <el-statistic :value="products.length" title="产品总数">
              <template #prefix>
                <el-icon :size="20"><Box /></el-icon>
              </template>
            </el-statistic>
          </div>
        </div>
      </div>
    </template>

    <div class="product-management-content">
      <!-- 操作栏 -->
      <div class="action-bar">
        <div class="action-left">
          <el-button 
            type="primary" 
            size="large"
            @click="handleAdd"
            class="add-button"
            :icon="Plus"
          >
            添加产品
          </el-button>
        </div>
        <div class="action-right">
          <el-tag type="info" size="large" effect="dark">
            共 {{ products.length }} 个产品
          </el-tag>
        </div>
      </div>

      <!-- 产品表格 -->
      <div class="table-wrapper">
        <el-table
          v-loading="loading"
          :data="products"
          border
          stripe
          class="product-table"
          :max-height="tableMaxHeight"
          empty-text="暂无产品数据，点击添加产品开始创建"
          :header-cell-style="{ 
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            color: '#fff',
            fontWeight: 'bold',
            fontSize: '14px',
            height: '44px',
            padding: '10px 0'
          }"
        >
          <el-table-column prop="id" label="ID" :width="isMobile ? 40 : 80" align="center" class-name="id-column">
            <template #default="scope">
              <el-tag type="info" effect="plain" :size="isMobile ? 'small' : 'small'">{{ scope.row.id }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="产品名称" :min-width="isMobile ? 120 : 300" class-name="name-column">
            <template #default="scope">
              <div class="product-name-cell">
                <el-icon class="product-icon"><Box /></el-icon>
                <span class="product-name">{{ scope.row.name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="ecpm_deduct_ratio" :label="isMobile ? 'eCPM' : 'eCPM减扣比例'" :width="isMobile ? 65 : 120" align="center" class-name="ecpm-column">
            <template #default="scope">
              <el-tag type="warning" effect="dark" :size="isMobile ? 'small' : 'default'">
                {{ formatPercentage(scope.row.ecpm_deduct_ratio) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="revenue_deduct_ratio" :label="isMobile ? '收益' : '收益减扣比例'" :width="isMobile ? 60 : 100" align="center" class-name="revenue-column">
            <template #default="scope">
              <el-tag type="success" effect="dark" :size="isMobile ? 'small' : 'default'">
                {{ formatPercentage(scope.row.revenue_deduct_ratio) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="is_active" label="状态" :width="isMobile ? 60 : 80" align="center" class-name="status-column">
            <template #default="scope">
              <el-tag 
                :type="scope.row.is_active ? 'success' : 'danger'" 
                :size="isMobile ? 'small' : 'default'"
                effect="dark"
                :icon="scope.row.is_active ? CircleCheck : CircleClose"
              >
                {{ scope.row.is_active ? '活跃' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" :label="isMobile ? '时间' : '创建时间'" :width="isMobile ? 100 : 180" align="center" class-name="time-column">
            <template #default="scope">
              <div class="time-cell">
                <el-icon :size="isMobile ? 14 : 16"><Clock /></el-icon>
                <span>{{ formatDate(scope.row.created_at) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" :width="isMobile ? 100 : 280" :fixed="isMobile ? 'right' : 'right'" align="center" class-name="action-column">
            <template #default="scope">
              <div class="action-buttons" :class="{ 'mobile-actions': isMobile }">
                <el-button 
                  type="info" 
                  :size="isMobile ? 'small' : 'default'"
                  :icon="Clock"
                  @click="handleViewHistory(scope.row)"
                  class="action-btn history-btn"
                  :circle="isMobile"
                  :title="isMobile ? '历史' : ''"
                >
                  <span v-if="!isMobile">历史</span>
                </el-button>
                <el-button 
                  type="primary" 
                  :size="isMobile ? 'small' : 'default'"
                  :icon="Edit"
                  @click="handleEdit(scope.row)"
                  class="action-btn edit-btn"
                  :circle="isMobile"
                  :title="isMobile ? '编辑' : ''"
                >
                  <span v-if="!isMobile">编辑</span>
                </el-button>
                <el-button 
                  type="danger" 
                  :size="isMobile ? 'small' : 'default'"
                  :icon="Delete"
                  @click="handleDelete(scope.row.id)"
                  class="action-btn delete-btn"
                  :circle="isMobile"
                  :title="isMobile ? '删除' : ''"
                >
                  <span v-if="!isMobile">删除</span>
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 产品分配历史对话框 -->
    <ProductAssignmentHistoryDialog
      v-model="assignmentHistoryVisible"
      :product-id="selectedProductForHistory?.id"
      :product-name="selectedProductForHistory?.name"
    />

    <!-- 产品表单对话框 -->
    <el-dialog 
      v-model="formDialogVisible" 
      :title="formTitle" 
      :width="isMobile ? '95%' : '800px'"
      :close-on-click-modal="false"
      class="product-form-dialog"
    >
      <el-form 
        ref="formRef" 
        :model="formData" 
        :rules="formRules" 
        label-width="130px"
        class="product-form"
      >
        <el-form-item label="产品名称" prop="name" class="product-name-item">
          <div class="product-name-wrapper">
            <el-autocomplete
              v-model="formData.name"
              :fetch-suggestions="queryProductNames"
              placeholder="请选择或输入产品名称"
              clearable
              size="large"
              :loading="productNamesLoading"
              @select="handleProductNameSelect"
              @blur="handleProductNameBlur"
              @focus="loadProductNames"
              class="product-name-select"
              ref="productNameSelectRef"
              value-key="value"
              :trigger-on-focus="true"
            >
              <template #prefix>
                <el-icon :size="20"><Box /></el-icon>
              </template>
              <template #default="{ item }">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <el-icon :size="16"><Box /></el-icon>
                  <span>{{ item.value }}</span>
                </div>
              </template>
            </el-autocomplete>
            <div class="form-hint-container">
              <div class="form-hint" v-if="productNames.length > 0">
                <el-icon :size="16"><InfoFilled /></el-icon>
                <span>已找到 {{ productNames.length }} 个产品（包括关联管理员的客户和其他客户的产品），可选择或手动输入新名称。选择其他客户的产品时，将直接将该产品的客户归属改为当前客户。</span>
              </div>
              <div class="form-hint" v-else-if="productNamesLoading">
                <el-icon :size="16"><Loading /></el-icon>
                <span>正在加载产品名称...</span>
              </div>
              <div class="form-hint" v-else>
                <el-icon :size="16"><InfoFilled /></el-icon>
                <span>当前客户已有所有产品名称，或数据库中没有产品，请手动输入新名称</span>
              </div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="eCPM减扣比例" prop="ecpm_deduct_ratio">
          <div>
            <el-input-number
              v-model="formData.ecpm_deduct_ratio"
              :min="0"
              :max="1"
              :step="0.01"
              :precision="4"
              style="width: 100%;"
              placeholder="0.00-1.00"
              size="large"
              controls-position="right"
            ></el-input-number>
            <div class="form-hint">
              <el-icon :size="16"><InfoFilled /></el-icon>
              <span>范围：0.00 - 1.00（例如：0.10 表示 10%）</span>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="收益减扣比例" prop="revenue_deduct_ratio">
          <div>
            <el-input-number
              v-model="formData.revenue_deduct_ratio"
              :min="0"
              :max="1"
              :step="0.01"
              :precision="4"
              style="width: 100%;"
              placeholder="0.00-1.00"
              size="large"
              controls-position="right"
            ></el-input-number>
            <div class="form-hint">
              <el-icon :size="16"><InfoFilled /></el-icon>
              <span>范围：0.00 - 1.00（例如：0.10 表示 10%）</span>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <div class="status-wrapper">
            <el-switch
              v-model="formData.is_active"
              active-text="活跃"
              inactive-text="禁用"
              size="large"
              aria-label="切换产品状态"
            ></el-switch>
            <div class="form-hint">
              <el-icon :size="16"><InfoFilled /></el-icon>
              <span>状态不活跃的产品在广告数据中将不会显示</span>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer-buttons">
          <el-button size="large" @click="formDialogVisible = false">取消</el-button>
          <el-button type="primary" size="large" @click="handleSave" :loading="saving" :icon="saving ? undefined : Check">
            <span>保存</span>
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 产品转移日期选择对话框 -->
    <el-dialog
      v-model="transferDateDialogVisible"
      title="选择产品转移日期"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-form :model="transferDateForm" label-width="120px">
        <el-form-item label="上一个客户">
          <el-input :value="formatClientFullName(transferDateForm.oldClientFullInfo)" disabled></el-input>
        </el-form-item>
        <el-form-item label="开始日期" required>
          <el-date-picker
            v-model="transferDateForm.startDate"
            type="date"
            placeholder="选择开始日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%;"
            :disabled-date="(date) => date > new Date()"
            @change="handleStartDateChange"
          />
          <div style="margin-top: 8px; color: #909399; font-size: 12px;">
            新客户开始拥有该产品的日期（修改后会自动更新旧客户结束日期）
          </div>
        </el-form-item>
        <el-form-item label="最后一个客户结束日期">
          <el-date-picker
            v-model="transferDateForm.lastClientEndDate"
            type="date"
            placeholder="选择最后一个客户的结束日期（默认昨天）"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%;"
            :disabled-date="(date) => {
              // 不能选择未来日期
              if (date > new Date()) {
                return true;
              }
              // 结束日期不能小于最后一个客户的开始日期
              if (lastClientStartDate.value) {
                const startDate = new Date(lastClientStartDate.value);
                startDate.setHours(0, 0, 0, 0);
                const checkDate = new Date(date);
                checkDate.setHours(0, 0, 0, 0);
                return checkDate < startDate;
              }
              return false;
            }"
            @change="handleEndDateChange"
          />
          <div style="margin-top: 8px; color: #909399; font-size: 12px;">
            上一个客户拥有该产品的结束日期（修改后会自动更新新客户开始日期，不能小于该客户的开始日期：{{ lastClientStartDate ? formatDate(lastClientStartDate) : '未设置' }}）
          </div>
        </el-form-item>
        <el-form-item label="产品变更历史" v-if="productAssignments.length > 0">
          <div v-loading="loadingAssignments" style="max-height: 300px; overflow-y: auto; padding: 12px; background: #f5f7fa; border-radius: 4px;">
            <el-timeline>
              <el-timeline-item
                v-for="(assignment, index) in productAssignments"
                :key="assignment.id"
                :timestamp="formatAssignmentDateRange(assignment)"
                placement="top"
                :type="assignment.end_date ? 'success' : 'primary'"
              >
                <div style="padding: 8px 0;">
                  <div style="font-weight: bold; margin-bottom: 4px;">
                    {{ formatAssignmentClientFullName(assignment) }}
                    <el-tag v-if="!assignment.end_date" type="success" size="small" style="margin-left: 8px;">当前有效</el-tag>
                  </div>
                  <div style="font-size: 12px; color: #666;">
                    <div>开始日期：{{ formatDate(assignment.start_date) }}</div>
                    <div v-if="assignment.end_date">结束日期：{{ formatDate(assignment.end_date) }}</div>
                    <div v-else>状态：进行中</div>
                  </div>
                </div>
              </el-timeline-item>
            </el-timeline>
          </div>
        </el-form-item>
        <el-form-item label="变更日期详情">
          <div style="padding: 12px; background: #f5f7fa; border-radius: 4px; line-height: 1.8;">
            <div style="margin-bottom: 8px;"><strong>上一个客户：</strong>{{ formatClientFullName(transferDateForm.oldClientFullInfo) }}</div>
            <div style="margin-bottom: 8px;"><strong>上一个客户结束日期：</strong>{{ oldClientEndDate || '未设置' }}</div>
            <div style="margin-bottom: 8px;"><strong>新客户：</strong>{{ props.clientName }}</div>
            <div><strong>新客户开始日期：</strong>{{ transferDateForm.startDate || '未设置' }}</div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="transferDateDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmTransferDate" :disabled="!transferDateForm.startDate">确定</el-button>
        </div>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<script setup>
import { ref, watch, reactive, computed, onMounted, nextTick } from 'vue';
import { ElDialog, ElButton, ElTable, ElTableColumn, ElTag, ElForm, ElFormItem, ElInput, ElInputNumber, ElSwitch, ElIcon, ElMessage, ElMessageBox, ElStatistic, ElSelect, ElOption, ElAutocomplete, ElDatePicker, ElTimeline, ElTimelineItem } from 'element-plus';
import { Plus, Edit, Delete, Box, Clock, InfoFilled, Check, CircleCheck, CircleClose, Loading } from '@element-plus/icons-vue';
import { getAvailableProductNames, getProductDetail, getProductAssignments } from '../../api/product';
import { getClientDetail } from '../../api/client';
import { logger } from '../../utils/logger';
import { formatDate as formatDateWithTimezone } from '../../utils/dateFormat';
import { useDevice } from '../../composables/useDevice';
import ProductAssignmentHistoryDialog from './ProductAssignmentHistoryDialog.vue';

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  clientName: {
    type: String,
    default: '未知客户'
  },
  clientId: {
    type: Number,
    default: null
  },
  products: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(['update:modelValue', 'add', 'edit', 'delete', 'save', 'refresh']);

// 设备检测
const { isMobile, isTablet } = useDevice();

// 计算表格最大高度
const tableMaxHeight = computed(() => {
  if (isMobile.value) {
    // 移动端：视口高度 - 对话框头部 - 操作栏 - 内边距
    // 头部约50px + 操作栏约80px + 内边距约20px = 约150px
    const viewportHeight = window.innerHeight || 667;
    return Math.max(200, viewportHeight - 150);
  }
  if (isTablet.value) {
    const viewportHeight = window.innerHeight || 768;
    return Math.max(400, viewportHeight - 200);
  }
  // 桌面端：根据视口高度动态计算，留出足够的头部和操作栏空间
  const viewportHeight = window.innerHeight;
  // 对话框头部约120px + 操作栏约80px + 内容padding约60px = 约260px
  return Math.max(400, viewportHeight - 260);
});

const visible = ref(props.modelValue);
const formDialogVisible = ref(false);
const formTitle = ref('添加产品');
const saving = ref(false);
const currentProductId = ref(null);
const assignmentHistoryVisible = ref(false);
const selectedProductForHistory = ref(null);
const formRef = ref(null);
const productNameSelectRef = ref(null);
const transferDateDialogVisible = ref(false);
const transferDateForm = reactive({
  oldClientId: null,
  oldClientName: '',
  oldClientFullInfo: null,  // 上一个客户的完整信息
  startDate: null,  // 开始日期（新客户开始拥有该产品的日期）
  lastClientEndDate: null  // 最后一个客户的结束日期（可选择）
});
const pendingTransferData = ref(null); // 保存待处理的产品转移数据
const productAssignments = ref([]); // 产品分配历史
const loadingAssignments = ref(false); // 加载历史记录状态
const lastClientStartDate = ref(null); // 最后一个客户的开始日期
const clientDetailCache = ref(new Map()); // 客户详情缓存，避免重复请求
const productAssignmentsCache = ref(new Map()); // 产品分配历史缓存，避免重复请求
const fetchingClientDetail = ref(new Set()); // 正在获取的客户详情ID集合，避免并发请求
const fetchingAssignments = ref(new Set()); // 正在获取的产品分配历史ID集合，避免并发请求

// 计算上一个客户的结束日期（如果用户没有手动选择，则使用开始日期 - 1天）
const oldClientEndDate = computed(() => {
  // 如果用户手动选择了最后一个客户的结束日期，使用用户选择的值
  if (transferDateForm.lastClientEndDate) {
    return transferDateForm.lastClientEndDate;
  }
  // 否则自动计算：开始日期 - 1天
  if (!transferDateForm.startDate) {
    return '';
  }
  const startDate = new Date(transferDateForm.startDate);
  startDate.setDate(startDate.getDate() - 1);
  const year = startDate.getFullYear();
  const month = String(startDate.getMonth() + 1).padStart(2, '0');
  const day = String(startDate.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
});

// 格式化客户全名
const formatClientFullName = (clientInfo) => {
  if (!clientInfo) return '未知客户';
  
  const parts = [];
  if (clientInfo.company_name) {
    parts.push(clientInfo.company_name);
  }
  if (clientInfo.contact_person) {
    parts.push(`(${clientInfo.contact_person})`);
  }
  if (clientInfo.phone) {
    parts.push(`- ${clientInfo.phone}`);
  }
  
  return parts.length > 0 ? parts.join(' ') : '未知客户';
};

// 获取今天的日期字符串
const getTodayDateString = () => {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, '0');
  const day = String(today.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// 获取昨天的日期字符串
const getYesterdayDateString = () => {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const year = yesterday.getFullYear();
  const month = String(yesterday.getMonth() + 1).padStart(2, '0');
  const day = String(yesterday.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// 产品相关状态
const productNames = ref([]); // 存储产品对象列表 {id, name, client_id}
const productNamesLoading = ref(false);
// 保存用户输入的产品名称备份（防止被清空）
const productNameBackup = ref('');
// 保存选中的产品对象（如果从下拉列表选择）
const selectedProduct = ref(null);

const formData = reactive({
  name: '',
  ecpm_deduct_ratio: 0,
  revenue_deduct_ratio: 0,
  is_active: true
});

// 监听 formData.name 的变化，更新备份
watch(() => formData.name, (newValue) => {
  // 如果新值不为空，更新备份
  if (newValue && String(newValue).trim() !== '') {
    const trimmedValue = String(newValue).trim();
    if (trimmedValue !== productNameBackup.value) {
      productNameBackup.value = trimmedValue;
    }
  }
}, { immediate: true });

// el-autocomplete 的查询函数
const queryProductNames = (queryString, cb) => {
  // 加载产品名称列表（如果还没有加载）
  if (productNames.value.length === 0 && !productNamesLoading.value) {
    loadProductNames().then(() => {
      filterAndReturnSuggestions(queryString, cb);
    });
  } else {
    filterAndReturnSuggestions(queryString, cb);
  }
};

// 过滤并返回建议列表
const filterAndReturnSuggestions = (queryString, cb) => {
  // productNames.value 现在是产品对象数组 {id, name, client_id}
  const results = queryString
    ? productNames.value.filter(product => 
        product.name.toLowerCase().includes(queryString.toLowerCase())
      ).map(product => ({ 
        value: product.name,
        product: product // 保存完整的产品对象
      }))
    : productNames.value.map(product => ({ 
        value: product.name,
        product: product
      }));
  
  // 如果用户输入的值不在列表中，也添加到建议列表（允许手动输入新名称）
  if (queryString && queryString.trim() !== '') {
    const trimmedQuery = queryString.trim();
    const exists = results.some(item => item.value === trimmedQuery);
    if (!exists) {
      results.unshift({ 
        value: trimmedQuery,
        product: null // 手动输入的新名称，没有对应的产品对象
      });
    }
  }
  
  cb(results);
};

const formRules = {
  name: [
    { required: true, message: '请输入产品名称', trigger: 'blur' },
    { min: 2, max: 100, message: '产品名称长度在 2 到 100 个字符', trigger: 'blur' }
  ],
  ecpm_deduct_ratio: [
    { required: true, message: '请输入eCPM减扣比例', trigger: 'blur' },
    { type: 'number', min: 0, max: 1, message: 'eCPM减扣比例范围：0.00 - 1.00', trigger: 'blur' }
  ],
  revenue_deduct_ratio: [
    { required: true, message: '请输入收益减扣比例', trigger: 'blur' },
    { type: 'number', min: 0, max: 1, message: '收益减扣比例范围：0.00 - 1.00', trigger: 'blur' }
  ]
};

watch(() => props.modelValue, (val) => {
  visible.value = val;
});

watch(visible, (val) => {
  emit('update:modelValue', val);
});

const formatDate = (dateString) => {
  // 使用统一的时区格式化函数
  return formatDateWithTimezone(dateString);
};

const formatPercentage = (value) => {
  return ((value || 0) * 100).toFixed(2) + '%';
};

const handleClose = () => {
  visible.value = false;
  emit('refresh');
};

// 加载产品名称列表
const loadProductNames = async () => {
  if (productNames.value.length > 0) {
    return; // 已加载过，不再重复加载
  }
  
  try {
    productNamesLoading.value = true;
    const result = await getAvailableProductNames(props.clientId);
    productNames.value = result.data || [];
  } catch (error) {
    // 加载产品名称失败，已在catch中处理
    productNames.value = [];
  } finally {
    productNamesLoading.value = false;
  }
};

// 产品名称选择处理（用户从下拉列表选择时触发）
const handleProductNameSelect = async (item) => {
  if (item && item.value) {
    const selectedValue = String(item.value).trim();
    productNameBackup.value = selectedValue;
    formData.name = selectedValue;
    
    // 保存选中的产品对象（如果是从列表选择的）
    if (item.product) {
      selectedProduct.value = item.product;
      
      // 如果选择了其他客户的产品，自动加载原产品的减扣比例和分配历史
      if (selectedProduct.value.client_id !== props.clientId) {
        try {
          // 使用 silent 选项，避免显示错误消息（因为这不是关键操作）
          const originalProduct = await getProductDetail(selectedProduct.value.id, { silent: true });
          
          if (originalProduct) {
            formData.ecpm_deduct_ratio = originalProduct.ecpm_deduct_ratio || 0;
            formData.revenue_deduct_ratio = originalProduct.revenue_deduct_ratio || 0;
          }
          
          // 获取上一个客户的完整信息（使用缓存避免重复请求）
          let oldClientFullInfo = null;
          const clientId = selectedProduct.value.client_id;
          
          // 检查缓存
          if (clientDetailCache.value.has(clientId)) {
            oldClientFullInfo = clientDetailCache.value.get(clientId);
          } else if (!fetchingClientDetail.value.has(clientId)) {
            // 如果不在缓存中且没有正在获取，则获取
            fetchingClientDetail.value.add(clientId);
            try {
              // 使用 silent 选项，避免显示错误消息（因为这不是关键操作）
              const clientDetail = await getClientDetail(clientId, { silent: true, useCache: true });
              if (clientDetail) {
                oldClientFullInfo = clientDetail;
                // 更新本地缓存（API层已有全局缓存，这里只是同步）
                clientDetailCache.value.set(clientId, clientDetail);
              }
            } catch (error) {
              logger.warn('获取客户详情失败:', error);
              // 429错误不缓存，其他错误可以缓存空值避免重复请求
              if (error.response?.status !== 429) {
                clientDetailCache.value.set(clientId, null);
              }
            } finally {
              fetchingClientDetail.value.delete(clientId);
            }
          } else {
            // 正在获取中，等待一小段时间后重试（最多等待1秒）
            let retries = 0;
            while (fetchingClientDetail.value.has(clientId) && retries < 10) {
              await new Promise(resolve => setTimeout(resolve, 100));
              retries++;
              if (clientDetailCache.value.has(clientId)) {
                oldClientFullInfo = clientDetailCache.value.get(clientId);
                break;
              }
            }
          }
          
          // 设置转移日期表单的初始值
          transferDateForm.oldClientId = selectedProduct.value.client_id;
          transferDateForm.oldClientName = oldClientFullInfo ? formatClientFullName(oldClientFullInfo) : '未知客户';
          transferDateForm.oldClientFullInfo = oldClientFullInfo;
          transferDateForm.startDate = getTodayDateString(); // 默认今天
          transferDateForm.lastClientEndDate = getYesterdayDateString(); // 默认昨天
          
          // 立即获取产品分配历史，以便用户查看变更记录（使用缓存避免重复请求）
          await fetchProductAssignments(selectedProduct.value.id, true); // 第二个参数表示使用缓存
        } catch (error) {
          // 静默处理错误，不显示给用户，因为这不是关键操作
          // 如果获取失败，用户仍然可以手动输入减扣比例
          logger.warn('handleProductNameSelect: 获取原产品信息失败:', error);
          // 不显示错误消息，避免干扰用户操作
        }
      } else {
        // 选择了当前客户的产品，清空分配历史
        productAssignments.value = [];
        lastClientStartDate.value = null;
      }
    } else {
      // 手动输入的新名称，清空选中的产品对象和分配历史
      selectedProduct.value = null;
      productAssignments.value = [];
      lastClientStartDate.value = null;
    }
  }
};


// 产品名称失去焦点处理（确保用户输入的值被保存）
const handleProductNameBlur = () => {
  // el-autocomplete 不会清空用户输入的值，但为了保险，更新备份
  if (formData.name && formData.name.trim() !== '') {
    productNameBackup.value = String(formData.name).trim();
    
    // 检查当前输入的名称是否匹配某个产品对象
    const matchedProduct = productNames.value.find(p => p.name === productNameBackup.value);
    if (matchedProduct) {
      selectedProduct.value = matchedProduct;
    } else {
      selectedProduct.value = null; // 手动输入的新名称
    }
  } else if (productNameBackup.value && productNameBackup.value.trim() !== '') {
    // 如果 formData.name 被清空但备份有值，恢复它
    formData.name = productNameBackup.value;
  }
};





const handleAdd = async () => {
  currentProductId.value = null;
  formTitle.value = '添加产品';
  Object.assign(formData, {
    name: '',
    ecpm_deduct_ratio: 0,
    revenue_deduct_ratio: 0,
    is_active: true
  });
  
  // 重置备份值和选中的产品对象
  productNameBackup.value = '';
  selectedProduct.value = null;
  
  // 加载产品列表
  await loadProductNames();
  
  if (formRef.value) {
    formRef.value.clearValidate();
  }
  formDialogVisible.value = true;
};

const handleEdit = async (product) => {
  currentProductId.value = product.id;
  formTitle.value = '编辑产品';
  
  // 编辑时也加载产品名称列表（用于参考）
  await loadProductNames();
  
  Object.assign(formData, {
    name: product.name || '',
    ecpm_deduct_ratio: product.ecpm_deduct_ratio || 0,
    revenue_deduct_ratio: product.revenue_deduct_ratio || 0,
    is_active: product.is_active !== undefined ? product.is_active : true
  });
  
  
  if (formRef.value) {
    formRef.value.clearValidate();
  }
  formDialogVisible.value = true;
};

const handleSave = async () => {
  if (!formRef.value) {
    logger.error('handleSave: formRef 不存在');
    return;
  }
  
  // 强制从多个来源获取产品名称（优先级：ref > DOM > formData）
  let productName = '';
  
  // 方法1: 从 el-autocomplete ref 获取
  if (productNameSelectRef.value) {
    try {
      // 尝试多种方式获取值
      let refValue = productNameSelectRef.value.selectedLabel || 
                     productNameSelectRef.value.value ||
                     productNameSelectRef.value.selected?.label;
      
      // 如果还没有值，尝试从 $el 获取（需要检查 $el 是否存在且是 DOM 元素）
      if (!refValue && productNameSelectRef.value.$el) {
        const $el = productNameSelectRef.value.$el;
        // 检查 $el 是否是 DOM 元素（有 querySelector 方法）
        if ($el && typeof $el.querySelector === 'function') {
          try {
            const inputElement = $el.querySelector('.el-input__inner');
            if (inputElement && inputElement.value) {
              refValue = inputElement.value;
            }
          } catch (domError) {
            // DOM 查询失败，忽略错误
          }
        }
      }
      
      if (refValue && String(refValue).trim() !== '') {
        productName = String(refValue).trim();
      }
    } catch (e) {
      logger.warn('handleSave: 从 ref 获取值失败:', e);
    }
  }
  
  // 方法2: 从 DOM 输入框获取
  if (!productName || productName.trim() === '') {
    const selectInput = document.querySelector('.product-name-select .el-input__inner');
    if (selectInput && selectInput.value && selectInput.value.trim() !== '') {
      productName = selectInput.value.trim();
    }
  }
  
  // 方法3: 从 formData 获取（作为最后备用）
  if (!productName || productName.trim() === '') {
    if (formData.name && String(formData.name).trim() !== '') {
      productName = String(formData.name).trim();
    }
  }
  
  // 更新 formData.name（确保值被设置）
  if (productName && productName.trim() !== '') {
    formData.name = productName;
  } else {
    logger.error('handleSave: 无法获取产品名称，所有方法都失败');
    ElMessage.error('请输入产品名称');
    return;
  }
  
  // 保存产品名称备份
  const savedProductName = formData.name ? String(formData.name).trim() : '';
  
  try {
    // 表单验证
    await formRef.value.validate();
    
    // 验证后再次检查产品名称
    if (!formData.name || String(formData.name).trim() === '') {
      if (savedProductName) {
        formData.name = savedProductName;
        await formRef.value.validate();
      } else {
        logger.error('handleSave: 产品名称为空且无法恢复');
        ElMessage.error('请输入产品名称');
        return;
      }
    }
    
    // 如果选择了其他客户的产品，先提示用户确认
    let productIdToUpdate = currentProductId.value; // 编辑模式时使用当前产品ID
    let isTransferProduct = false; // 标记是否是转移产品（只更新 client_id）
    
    // 如果已经有待处理的转移数据且已选择日期，跳过日期选择对话框
    if (pendingTransferData.value && pendingTransferData.value.endDate) {
      // 已经有日期，直接继续保存流程
      isTransferProduct = true;
      productIdToUpdate = pendingTransferData.value.productId;
    } else if (selectedProduct.value && selectedProduct.value.client_id !== props.clientId) {
      // 选择了其他客户的产品，需要用户确认并选择日期
      // 检查是否已经有待处理的转移数据（避免重复设置）
      if (!pendingTransferData.value || pendingTransferData.value.productId !== selectedProduct.value.id) {
        try {
          // 获取上一个客户的完整信息（使用缓存避免重复请求）
          let oldClientName = '未知客户';
          let oldClientFullInfo = null;
          const clientId = selectedProduct.value.client_id;
          
          // 检查缓存
          if (clientDetailCache.value.has(clientId)) {
            oldClientFullInfo = clientDetailCache.value.get(clientId);
            if (oldClientFullInfo) {
              oldClientName = formatClientFullName(oldClientFullInfo);
            }
          } else if (!fetchingClientDetail.value.has(clientId)) {
            // 如果不在缓存中且没有正在获取，则获取
            fetchingClientDetail.value.add(clientId);
            try {
              // 使用 silent 选项，避免显示错误消息（因为这不是关键操作）
              const clientDetail = await getClientDetail(clientId, { silent: true, useCache: true });
              if (clientDetail) {
                oldClientFullInfo = clientDetail;
                oldClientName = formatClientFullName(clientDetail);
                // 更新本地缓存（API层已有全局缓存，这里只是同步）
                clientDetailCache.value.set(clientId, clientDetail);
              }
            } catch (error) {
              logger.warn('获取客户详情失败:', error);
              // 429错误不缓存，其他错误可以缓存空值避免重复请求
              if (error.response?.status !== 429) {
                clientDetailCache.value.set(clientId, null);
              }
            } finally {
              fetchingClientDetail.value.delete(clientId);
            }
          } else {
            // 正在获取中，等待一小段时间后重试（最多等待1秒）
            let retries = 0;
            while (fetchingClientDetail.value.has(clientId) && retries < 10) {
              await new Promise(resolve => setTimeout(resolve, 100));
              retries++;
              if (clientDetailCache.value.has(clientId)) {
                oldClientFullInfo = clientDetailCache.value.get(clientId);
                if (oldClientFullInfo) {
                  oldClientName = formatClientFullName(oldClientFullInfo);
                }
                break;
              }
            }
          }
          
          // 保存转移数据
          pendingTransferData.value = {
            productId: selectedProduct.value.id,
            oldClientId: selectedProduct.value.client_id,
            oldClientName: oldClientName,
            oldClientFullInfo: oldClientFullInfo,
            newClientId: props.clientId,
            newClientName: props.clientName,
            productName: selectedProduct.value.name
          };
          
          // 设置转移日期表单，默认值：新客户开始日期为今天，上一个客户结束日期默认昨天
          transferDateForm.oldClientId = selectedProduct.value.client_id;
          transferDateForm.oldClientName = oldClientName;
          transferDateForm.oldClientFullInfo = oldClientFullInfo;
          transferDateForm.startDate = getTodayDateString(); // 默认今天
          transferDateForm.lastClientEndDate = getYesterdayDateString(); // 默认昨天
          
          // 获取产品分配历史
          await fetchProductAssignments(selectedProduct.value.id);
        } catch (error) {
          logger.warn('设置转移数据失败:', error);
        }
      }
      
      // 如果还没有选择日期，显示日期选择对话框
      if (!transferDateForm.startDate) {
        // 确保产品分配历史已加载（如果还没有，使用缓存避免重复请求）
        if (selectedProduct.value && productAssignments.value.length === 0) {
          try {
            await fetchProductAssignments(selectedProduct.value.id, true);
          } catch (error) {
            logger.warn('打开日期选择对话框时获取产品分配历史失败:', error);
            // 即使获取失败，也继续显示对话框
          }
        }
        transferDateDialogVisible.value = true;
        // 等待用户选择日期（通过 confirmTransferDate 函数继续）
        return;
      }
    }
    
    saving.value = true;
    
    const submitData = {
      name: String(formData.name).trim(),
      ecpm_deduct_ratio: formData.ecpm_deduct_ratio,
      revenue_deduct_ratio: formData.revenue_deduct_ratio,
      is_active: formData.is_active,
      client_id: props.clientId  // 新的客户ID
    };
    
    // 如果是转移产品（只更改 client_id），只提交 client_id 和 transfer_date，其他字段保持不变
    if (pendingTransferData.value) {
      isTransferProduct = true;
      productIdToUpdate = pendingTransferData.value.productId;
      
      // 只更新 client_id、transfer_date 和 old_client_end_date，删除其他字段（不发送到后端）
      delete submitData.name;
      delete submitData.ecpm_deduct_ratio;
      delete submitData.revenue_deduct_ratio;
      delete submitData.is_active;
      
      // 添加 transfer_date（新客户开始日期）和 old_client_end_date（旧客户结束日期）
      if (pendingTransferData.value.startDate) {
        submitData.transfer_date = pendingTransferData.value.startDate;
      }
      if (pendingTransferData.value.endDate) {
        submitData.old_client_end_date = pendingTransferData.value.endDate;
      }
    }
    
    // 最终验证（如果是转移产品，只验证 client_id）
    if (!isTransferProduct) {
      // 创建或编辑产品时，需要验证所有字段
      if (!submitData.name || submitData.name.trim() === '') {
        logger.error('handleSave: 提交数据中产品名称为空');
        ElMessage.error('请输入产品名称');
        saving.value = false;
        return;
      }
      
      if (submitData.ecpm_deduct_ratio === undefined || submitData.ecpm_deduct_ratio === null) {
        ElMessage.error('请输入eCPM减扣比例');
        saving.value = false;
        return;
      }
      
      if (submitData.revenue_deduct_ratio === undefined || submitData.revenue_deduct_ratio === null) {
        ElMessage.error('请输入收益减扣比例');
        saving.value = false;
        return;
      }
    } else {
      // 转移产品时，只需要验证 client_id 存在
      if (!submitData.client_id) {
        logger.error('handleSave: 客户ID为空');
        ElMessage.error('客户ID不能为空');
        saving.value = false;
        return;
      }
    }
    
    // 发出保存事件，并等待保存完成
    // 使用 Promise 来等待保存操作完成
    let callbackCalled = false;
    const savePromise = new Promise((resolve, reject) => {
      // 发出保存事件，传递回调函数
      // 如果选择了其他客户的产品，使用原产品的ID进行更新
      const finalProductId = productIdToUpdate || currentProductId.value;
      emit('save', {
        id: finalProductId,  // 如果选择了其他客户的产品，使用原产品ID
        data: submitData,
        callback: (success) => {
          callbackCalled = true;
          if (success) {
            resolve(true);
          } else {
            reject(new Error('保存失败'));
          }
        }
      });
      
      // 设置超时，防止回调永远不执行
      setTimeout(() => {
        if (!callbackCalled) {
          logger.error('handleSave: 保存操作超时，回调未执行');
          reject(new Error('保存操作超时'));
        }
      }, 10000); // 10秒超时
    });
    
    // 等待保存完成
    await savePromise;
    
    // 保存成功后才关闭对话框
    formDialogVisible.value = false;
    
    // 重置表单
    Object.assign(formData, {
      name: '',
      ecpm_deduct_ratio: 0,
      revenue_deduct_ratio: 0,
      is_active: true
    });
    currentProductId.value = null;
    
    // 清空产品列表，下次打开时会重新加载（排除新添加的产品）
    productNames.value = [];
    selectedProduct.value = null;
    
    // 清空转移数据
    pendingTransferData.value = null;
    transferDateForm.startDate = null;
    transferDateForm.lastClientEndDate = null;
    transferDateForm.oldClientFullInfo = null;
    productAssignments.value = [];
    lastClientStartDate.value = null;
    
  } catch (error) {
    // 表单验证失败或保存失败
    // 如果产品名称在验证过程中丢失，尝试恢复
    if (!formData.name && savedProductName) {
      formData.name = savedProductName;
    }
    // 不关闭对话框，让用户看到错误
    // 错误消息已在 saveProduct 中显示
  } finally {
    saving.value = false;
  }
};

// 格式化分配历史日期范围
const formatAssignmentDateRange = (assignment) => {
  if (assignment.end_date) {
    return `${formatDate(assignment.start_date)} - ${formatDate(assignment.end_date)}`;
  } else {
    return `${formatDate(assignment.start_date)} - 至今`;
  }
};

// 格式化产品分配历史中的客户全名（优先显示用户全名，如果没有则显示公司名称、联系人、电话）
const formatAssignmentClientFullName = (assignment) => {
  if (!assignment) return '未知客户';
  
  // 优先显示用户全名
  if (assignment.user_full_name) {
    return assignment.user_full_name;
  }
  
  // 如果没有用户全名，显示公司名称、联系人、电话
  const parts = [];
  if (assignment.company_name) {
    parts.push(assignment.company_name);
  }
  if (assignment.contact_person) {
    parts.push(`(${assignment.contact_person})`);
  }
  if (assignment.phone) {
    parts.push(`- ${assignment.phone}`);
  }
  
  return parts.length > 0 ? parts.join(' ') : (assignment.client_name || '未知客户');
};

// 处理开始日期变化（自动更新结束日期）
const handleStartDateChange = (value) => {
  if (value) {
    // 新客户开始日期变化时，自动更新旧客户结束日期 = 开始日期 - 1天
    const startDate = new Date(value);
    startDate.setDate(startDate.getDate() - 1);
    const year = startDate.getFullYear();
    const month = String(startDate.getMonth() + 1).padStart(2, '0');
    const day = String(startDate.getDate()).padStart(2, '0');
    transferDateForm.lastClientEndDate = `${year}-${month}-${day}`;
  }
};

// 处理结束日期变化（自动更新开始日期）
const handleEndDateChange = (value) => {
  if (value) {
    // 旧客户结束日期变化时，自动更新新客户开始日期 = 结束日期 + 1天
    const endDate = new Date(value);
    endDate.setDate(endDate.getDate() + 1);
    const year = endDate.getFullYear();
    const month = String(endDate.getMonth() + 1).padStart(2, '0');
    const day = String(endDate.getDate()).padStart(2, '0');
    transferDateForm.startDate = `${year}-${month}-${day}`;
  }
};

// 获取产品分配历史
const fetchProductAssignments = async (productId, useCache = false) => {
  if (!productId) return;
  
  // 如果使用缓存且缓存中有数据，直接使用
  if (useCache && productAssignmentsCache.value.has(productId)) {
    const cachedAssignments = productAssignmentsCache.value.get(productId);
    productAssignments.value = cachedAssignments;
    // 更新最后一个客户的开始日期
    if (productAssignments.value.length > 0) {
      const currentAssignment = productAssignments.value.find(a => !a.end_date) || productAssignments.value[0];
      if (currentAssignment) {
        lastClientStartDate.value = currentAssignment.start_date;
      }
    }
    return;
  }
  
  // 如果正在获取中，等待
  if (fetchingAssignments.value.has(productId)) {
    let retries = 0;
    while (fetchingAssignments.value.has(productId) && retries < 10) {
      await new Promise(resolve => setTimeout(resolve, 100));
      retries++;
      if (productAssignmentsCache.value.has(productId)) {
        const cachedAssignments = productAssignmentsCache.value.get(productId);
        productAssignments.value = cachedAssignments;
        // 更新最后一个客户的开始日期
        if (productAssignments.value.length > 0) {
          const currentAssignment = productAssignments.value.find(a => !a.end_date) || productAssignments.value[0];
          if (currentAssignment) {
            lastClientStartDate.value = currentAssignment.start_date;
          }
        }
        return;
      }
    }
  }
  
  loadingAssignments.value = true;
  fetchingAssignments.value.add(productId);
  
  try {
    const result = await getProductAssignments(productId);
    // 确保数据结构正确
    // API返回格式：{ code: 200, data: { data: [...], total: ... } }
    // 或者：{ code: 200, data: [...] }
    let assignments = [];
    if (result && result.data) {
      if (Array.isArray(result.data)) {
        assignments = result.data;
      } else if (result.data.data && Array.isArray(result.data.data)) {
        assignments = result.data.data;
      } else if (result.data && Array.isArray(result.data)) {
        assignments = result.data;
      }
    }
    
    // 按开始日期排序（最新的在前）
    assignments.sort((a, b) => {
      const dateA = new Date(a.start_date);
      const dateB = new Date(b.start_date);
      return dateB - dateA; // 降序排列
    });
    
    productAssignments.value = assignments;
    
    // 缓存结果（最多缓存10个产品的历史）
    if (productAssignmentsCache.value.size >= 10) {
      // 删除最旧的缓存（FIFO）
      const firstKey = productAssignmentsCache.value.keys().next().value;
      productAssignmentsCache.value.delete(firstKey);
    }
    productAssignmentsCache.value.set(productId, assignments);
    
    // 获取最后一个客户的开始日期（用于验证）
    if (productAssignments.value.length > 0) {
      // 找到当前有效的分配记录（end_date为null）或最新的记录
      const currentAssignment = productAssignments.value.find(a => !a.end_date) || productAssignments.value[0];
      if (currentAssignment) {
        lastClientStartDate.value = currentAssignment.start_date;
      }
      
      logger.info(`成功获取产品 ${productId} 的分配历史，共 ${productAssignments.value.length} 条记录`);
    } else {
      logger.warn(`产品 ${productId} 没有分配历史记录`);
    }
  } catch (error) {
    logger.warn('获取产品分配历史失败:', error);
    productAssignments.value = [];
    // 429错误不缓存，其他错误可以缓存空数组避免重复请求
    if (error.response?.status !== 429) {
      productAssignmentsCache.value.set(productId, []);
    }
    // 不显示错误消息，避免干扰用户操作
  } finally {
    loadingAssignments.value = false;
    fetchingAssignments.value.delete(productId);
  }
};

// 确认转移日期
const confirmTransferDate = async () => {
  if (!transferDateForm.startDate) {
    ElMessage.warning('请选择开始日期');
    return;
  }
  
  // 验证开始日期不能是未来日期
  const startDate = new Date(transferDateForm.startDate);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  startDate.setHours(0, 0, 0, 0);
  if (startDate > today) {
    ElMessage.warning('开始日期不能是未来日期');
    return;
  }
  
  // 确定最后一个客户的结束日期（用户选择的值或默认昨天）
  let lastClientEndDate = transferDateForm.lastClientEndDate;
  if (!lastClientEndDate) {
    // 如果没有选择，使用默认值（昨天）
    lastClientEndDate = getYesterdayDateString();
  }
  
  // 验证最后一个客户的结束日期不能小于该客户的开始日期
  if (lastClientStartDate.value) {
    const lastStartDate = new Date(lastClientStartDate.value);
    lastStartDate.setHours(0, 0, 0, 0);
    const endDate = new Date(lastClientEndDate);
    endDate.setHours(0, 0, 0, 0);
    if (endDate < lastStartDate) {
      ElMessage.warning(`最后一个客户的结束日期不能小于该客户的开始日期（${formatDate(lastClientStartDate.value)}）`);
      return;
    }
  }
  
  // 验证最后一个客户的结束日期不能小于新客户的开始日期
  const endDate = new Date(lastClientEndDate);
  endDate.setHours(0, 0, 0, 0);
  if (endDate < startDate) {
    ElMessage.warning('最后一个客户的结束日期不能小于新客户的开始日期');
    return;
  }
  
  // 验证日期连续性：新客户开始日期必须是旧客户结束日期 + 1天（确保无空窗期）
  const expectedStartDate = new Date(endDate);
  expectedStartDate.setDate(expectedStartDate.getDate() + 1);
  expectedStartDate.setHours(0, 0, 0, 0);
  
  if (startDate.getTime() !== expectedStartDate.getTime()) {
    const expectedDateStr = `${expectedStartDate.getFullYear()}-${String(expectedStartDate.getMonth() + 1).padStart(2, '0')}-${String(expectedStartDate.getDate()).padStart(2, '0')}`;
    ElMessage.warning(`日期连续性错误：新客户开始日期（${transferDateForm.startDate}）必须是旧客户结束日期（${lastClientEndDate}）+ 1天，期望值：${expectedDateStr}，以确保广告数据无空窗期`);
    return;
  }
  
  // 保存开始日期和结束日期到待处理数据
  if (pendingTransferData.value) {
    // 保存新客户开始日期
    pendingTransferData.value.startDate = transferDateForm.startDate;
    // 使用用户选择的结束日期或默认值
    pendingTransferData.value.endDate = lastClientEndDate;
  }
  
  // 关闭日期选择对话框
  transferDateDialogVisible.value = false;
  
  // 继续保存流程（直接调用保存逻辑，不再检查日期选择）
  // 创建一个新的保存函数来避免重复检查
  await continueSaveAfterDateSelection();
};

// 在日期选择后继续保存流程
const continueSaveAfterDateSelection = async () => {
  if (!pendingTransferData.value || !pendingTransferData.value.startDate || !pendingTransferData.value.endDate) {
    ElMessage.error('转移日期数据不完整，请重新操作');
    return;
  }
  
  saving.value = true;
  
  try {
    const submitData = {
      client_id: props.clientId,  // 新的客户ID
      transfer_date: pendingTransferData.value.startDate,  // 新客户开始日期
      old_client_end_date: pendingTransferData.value.endDate  // 旧客户结束日期
    };
    
    const productIdToUpdate = pendingTransferData.value.productId;
    
    // 发出保存事件，并等待保存完成
    let callbackCalled = false;
    const savePromise = new Promise((resolve, reject) => {
      emit('save', {
        id: productIdToUpdate,
        data: submitData,
        callback: (success) => {
          callbackCalled = true;
          if (success) {
            resolve(true);
          } else {
            reject(new Error('保存失败'));
          }
        }
      });
      
      // 设置超时，防止回调永远不执行
      setTimeout(() => {
        if (!callbackCalled) {
          logger.error('continueSaveAfterDateSelection: 保存操作超时，回调未执行');
          reject(new Error('保存操作超时'));
        }
      }, 10000); // 10秒超时
    });
    
    // 等待保存完成
    await savePromise;
    
    // 保存成功后才关闭对话框
    formDialogVisible.value = false;
    
    // 重置表单
    Object.assign(formData, {
      name: '',
      ecpm_deduct_ratio: 0,
      revenue_deduct_ratio: 0,
      is_active: true
    });
    currentProductId.value = null;
    
    // 清空产品列表，下次打开时会重新加载
    productNames.value = [];
    selectedProduct.value = null;
    
    // 清空转移数据
    pendingTransferData.value = null;
    transferDateForm.startDate = null;
    transferDateForm.lastClientEndDate = null;
    transferDateForm.oldClientFullInfo = null;
    productAssignments.value = [];
    lastClientStartDate.value = null;
    
  } catch (error) {
    // 保存失败
    logger.error('continueSaveAfterDateSelection: 保存失败:', error);
    // 不关闭对话框，让用户看到错误
  } finally {
    saving.value = false;
  }
};

const handleViewHistory = (product) => {
  selectedProductForHistory.value = product;
  assignmentHistoryVisible.value = true;
};

const handleDelete = async (id) => {
  try {
    await ElMessageBox.confirm(
      '确定要删除此产品吗？此操作不可撤销，且会删除关联的广告数据。',
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
        icon: 'Warning',
        appendTo: document.body, // 确保弹窗附加到 body，避免被对话框遮挡
        zIndex: 3001 // 确保 z-index 高于对话框
      }
    );
    emit('delete', id);
  } catch (error) {
    // 用户取消
  }
};
</script>

<style scoped>
/* 对话框样式 */
.product-management-dialog :deep(.el-dialog) {
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  margin: 5vh auto !important;
  top: 0;
  transform: translateY(0);
}

.product-management-dialog :deep(.el-dialog__wrapper) {
  display: flex;
  align-items: center;
  justify-content: center;
}

.product-management-dialog :deep(.el-dialog__header) {
  padding: 0;
  margin: 0;
  border-bottom: none;
  flex-shrink: 0;
}

.product-management-dialog :deep(.el-dialog__body) {
  padding: 0;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* 对话框头部 */
.dialog-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 5px 40px;
  color: white;
  position: relative;
  overflow: hidden;
}

.dialog-header::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.1) 0%, transparent 70%);
  animation: pulse 3s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.5;
  }
  50% {
    transform: scale(1.1);
    opacity: 0.3;
  }
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: relative;
  z-index: 1;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.header-icon {
  font-size: 48px;
  opacity: 0.9;
  animation: float 3s ease-in-out infinite;
}

@keyframes float {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.header-title {
  margin: 0;
  font-size: var(--font-size-large-title);
  font-weight: var(--font-weight-bold);
  color: var(--text-white);
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.header-subtitle {
  margin: 0;
  font-size: var(--font-size-lg);
  opacity: 0.9;
  font-weight: var(--font-weight-normal);
}

.header-right {
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(10px);
  padding: var(--spacing-lg) var(--spacing-xxl);
  border-radius: var(--radius-xxl);
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.header-right :deep(.el-statistic__number) {
  color: var(--text-white);
  font-size: var(--font-size-title);
  font-weight: var(--font-weight-bold);
}

.header-right :deep(.el-statistic__head) {
  color: rgba(255, 255, 255, 0.9);
  font-size: var(--font-size-sm);
}

.header-right :deep(.el-icon) {
  color: var(--text-white);
  font-size: var(--font-size-xxl);
}

/* 内容区域 */
.product-management-content {
  padding: var(--spacing-lg) var(--spacing-xxxxl) var(--spacing-lg);
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  flex: 1;
  overflow: hidden;
}

/* 操作栏 */
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
  padding: 0 var(--spacing-xl);
  height: 50px;
  background: var(--bg-primary);
  border-radius: var(--radius-xxl);
  box-shadow: var(--shadow-light);
  flex-shrink: 0;
}

.add-button {
  height: 44px;
  padding: 0 var(--spacing-xxxl);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  border-radius: var(--radius-xl);
  background: linear-gradient(135deg, var(--primary-color) 0%, #764ba2 100%);
  border: none;
  box-shadow: var(--shadow-medium);
  transition: var(--transition-base);
}

.add-button:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-dark);
}

.action-right {
  display: flex;
  align-items: center;
  gap: 15px;
}

/* 表格包装器 */
.table-wrapper {
  background: var(--bg-primary);
  border-radius: var(--radius-xxl);
  padding: var(--spacing-lg);
  box-shadow: var(--shadow-light);
  overflow: hidden;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  margin-bottom: 0;
}

.product-table {
  border-radius: var(--radius-lg);
  overflow: hidden;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.product-table :deep(.el-table) {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.product-table :deep(.el-table__header-wrapper) {
  flex-shrink: 0;
}

.product-table :deep(.el-table__body-wrapper) {
  flex: 1;
  overflow-y: auto !important;
  overflow-x: hidden !important;
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
  min-height: 0;
  max-height: 100%;
}

/* 优化滚动条样式 */
.product-table :deep(.el-table__body-wrapper)::-webkit-scrollbar {
  width: 8px;
}

.product-table :deep(.el-table__body-wrapper)::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.product-table :deep(.el-table__body-wrapper)::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 4px;
}

.product-table :deep(.el-table__body-wrapper)::-webkit-scrollbar-thumb:hover {
  background: #555;
}

.product-table :deep(.el-table__row) {
  transition: all 0.2s ease;
}

.product-table :deep(.el-table__row:hover) {
  background-color: #f5f7fa;
}

.product-table :deep(.el-table td) {
  padding: 12px 0;
}

.product-table :deep(.el-table th) {
  padding: 12px 0;
}

/* 产品名称单元格 */
.product-name-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.product-icon {
  font-size: var(--font-size-xl);
  color: var(--primary-color);
}

.product-name {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  font-size: var(--font-size-md);
}

/* 时间单元格 */
.time-cell {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: var(--text-regular);
  font-size: var(--font-size-sm);
}

.time-cell .el-icon {
  color: var(--text-secondary);
}

/* 操作按钮 */
.action-buttons {
  display: flex;
  gap: 10px;
  justify-content: center;
}

.action-btn {
  padding: var(--spacing-sm) var(--spacing-lg);
  border-radius: var(--radius-md);
  font-weight: var(--font-weight-medium);
  transition: var(--transition-base);
}

.edit-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(64, 158, 255, 0.3);
}

.delete-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(245, 108, 108, 0.3);
}

/* 产品表单对话框 */
.product-form-dialog :deep(.el-dialog) {
  border-radius: var(--radius-xxl);
}

.product-form-dialog :deep(.el-dialog__header) {
  padding: var(--spacing-xxl) var(--spacing-xxxl);
  border-bottom: 1px solid var(--border-lighter);
}

.product-form-dialog :deep(.el-dialog__body) {
  padding: var(--spacing-xxxl);
}

.product-form-dialog :deep(.el-dialog__footer) {
  padding: var(--spacing-xl) var(--spacing-xxxl);
  border-top: 1px solid var(--border-lighter);
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-md);
}

.product-form {
  padding: var(--spacing-xl) 0;
}

.product-form :deep(.el-form-item) {
  margin-bottom: var(--spacing-xxxl);
}

.product-form :deep(.el-form-item__label) {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-md);
  color: var(--text-primary);
  line-height: 40px;
}

.product-form :deep(.el-form-item__content) {
  line-height: 40px;
}

/* 产品名称表单项 */
.product-name-item {
  margin-bottom: var(--spacing-xxxl) !important;
}

.product-name-wrapper {
  width: 100%;
  min-height: 90px;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.product-name-select {
  width: 100% !important;
  min-width: 400px;
}

.product-name-select :deep(.el-input__wrapper) {
  transition: none !important;
}

.product-name-select :deep(.el-input__inner) {
  font-size: 14px;
  padding: 0 12px;
}

.form-hint-container {
  min-height: 40px;
  display: flex;
  align-items: flex-start;
  transition: none;
}

.form-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-top: 0;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  width: 100%;
  min-height: 32px;
  transition: none;
}

.form-hint .el-icon {
  color: var(--primary-color);
  font-size: var(--font-size-lg);
}

/* 状态字段包装器 */
.status-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  width: 100%;
}

.status-wrapper .el-switch {
  align-self: flex-start;
}

.status-wrapper .form-hint {
  margin-top: var(--spacing-xs);
  background-color: #fef0f0;
  border: 1px solid #fde2e2;
  color: #f56c6c;
}

.status-wrapper .form-hint .el-icon {
  color: #f56c6c;
}

.dialog-footer-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.dialog-footer-buttons .el-button {
  padding: 12px 28px;
  font-size: 15px;
  font-weight: 500;
  border-radius: 8px;
}

/* 响应式设计 */
@media (max-width: 1600px) {
  .product-management-dialog :deep(.el-dialog) {
    width: 95% !important;
    max-width: 1400px;
    margin: 5vh auto !important;
    top: 0;
    transform: translateY(0);
  }
}

@media (max-width: 767px) {
  /* 对话框移动端优化 */
  .product-management-dialog :deep(.el-dialog) {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    top: 0 !important;
    left: 0 !important;
    transform: none !important;
    max-height: 100vh;
    height: 100vh;
    border-radius: 0;
    display: flex;
    flex-direction: column;
  }
  
  .product-management-dialog :deep(.el-dialog__wrapper) {
    display: flex;
    align-items: stretch;
    justify-content: center;
    padding: 0;
  }
  
  .product-management-dialog :deep(.el-dialog__header) {
    padding: 12px 16px;
    flex-shrink: 0;
  }
  
  .product-management-dialog :deep(.el-dialog__body) {
    padding: 0;
    flex: 1;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  
  .product-management-dialog :deep(.el-dialog__footer) {
    padding: 12px 16px;
    flex-shrink: 0;
  }
  
  .product-management-dialog :deep(.el-dialog__headerbtn) {
    top: 12px;
    right: 16px;
    width: 44px;
    height: 44px;
    font-size: 20px;
  }

  /* 对话框头部移动端优化 - 更紧凑 */
  .dialog-header {
    padding: 8px 12px;
    min-height: 50px;
  }

  .header-content {
    flex-direction: column;
    gap: 12px;
    align-items: flex-start;
  }

  .header-left {
    width: 100%;
    gap: 12px;
  }

  .header-icon {
    font-size: 32px;
  }

  .header-title {
    font-size: 18px;
    line-height: 1.2;
  }
  
  .header-subtitle {
    font-size: 13px;
    line-height: 1.2;
  }

  .header-right {
    width: 100%;
    padding: 12px 16px;
    border-radius: 12px;
  }

  .header-right :deep(.el-statistic__number) {
    font-size: 24px;
  }

  .header-right :deep(.el-statistic__head) {
    font-size: 12px;
  }

  /* 内容区域移动端优化 - 更紧凑 */
  .product-management-content {
    padding: 8px 8px 0 8px;
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    height: 100%;
  }

  /* 操作栏移动端优化 - 更紧凑 */
  .action-bar {
    flex-direction: column;
    gap: 8px;
    align-items: stretch;
    margin-bottom: 8px;
    padding: 8px;
    height: auto;
    min-height: auto;
  }

  .action-left,
  .action-right {
    width: 100%;
  }

  .add-button {
    width: 100%;
    height: 48px;
    min-height: 48px;
    font-size: 16px;
    padding: 0 20px;
    border-radius: 12px;
  }

  .action-right .el-tag {
    width: 100%;
    justify-content: center;
    padding: 12px;
    font-size: 14px;
    border-radius: 12px;
  }

  /* 表格包装器移动端优化 - 更紧凑 */
  .table-wrapper {
    padding: 6px;
    flex: 1;
    min-height: 0;
    border-radius: 8px;
    margin-bottom: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  
  /* 表格移动端优化 */
  .product-table {
    font-size: 12px;
    border-radius: 8px;
    min-width: 100%;
    width: 100%;
  }

  .product-table :deep(.el-table) {
    min-width: 600px; /* 减小最小宽度，让表格更紧凑 */
    width: 100%;
  }

  .product-table :deep(.el-table__header-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: thin;
  }

  .product-table :deep(.el-table__body-wrapper) {
    overflow-x: auto;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: thin;
    flex: 1;
    min-height: 0;
    max-height: 100%;
  }

  /* 表格容器添加滚动提示 */
  .table-wrapper {
    position: relative;
    overflow: hidden;
  }

  .table-wrapper::after {
    content: '';
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    width: 30px;
    background: linear-gradient(to right, transparent, rgba(0, 0, 0, 0.05));
    pointer-events: none;
    z-index: 1;
  }

  /* 移动端滚动条优化 */
  .product-table :deep(.el-table__body-wrapper)::-webkit-scrollbar {
    width: 4px;
    height: 4px;
  }

  .product-table :deep(.el-table__body-wrapper)::-webkit-scrollbar-track {
    background: transparent;
  }

  .product-table :deep(.el-table__body-wrapper)::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 2px;
  }

  .product-table :deep(.el-table__body-wrapper)::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 0, 0, 0.3);
  }

  /* 表格空状态移动端优化 */
  .product-table :deep(.el-table__empty-block) {
    padding: 40px 20px;
  }

  .product-table :deep(.el-table__empty-text) {
    font-size: 14px;
    color: #909399;
  }
  
  .product-table :deep(.el-table__cell) {
    padding: 6px 4px;
    word-break: break-word;
    white-space: nowrap;
    min-width: 40px;
  }
  
  .product-table :deep(.el-table__header th) {
    font-size: 10px;
    padding: 6px 4px;
    white-space: nowrap;
    font-weight: 600;
    min-width: 40px;
  }
  
  .product-table :deep(.el-table__body td) {
    font-size: 10px;
    padding: 6px 4px;
    vertical-align: middle;
    white-space: nowrap;
    min-width: 40px;
  }

  /* ID列优化 - 更紧凑 */
  .product-table :deep(.id-column) {
    width: 40px !important;
    min-width: 40px !important;
    max-width: 40px !important;
  }

  /* 产品名称列优化 - 增加宽度显示更多内容 */
  .product-table :deep(.name-column) {
    min-width: 120px !important;
    max-width: 180px !important;
  }

  /* eCPM列优化 - 更紧凑 */
  .product-table :deep(.ecpm-column) {
    width: 65px !important;
    min-width: 65px !important;
    max-width: 65px !important;
  }

  /* 收益列优化 - 更紧凑 */
  .product-table :deep(.revenue-column) {
    width: 60px !important;
    min-width: 60px !important;
    max-width: 60px !important;
  }

  /* 状态列优化 - 更紧凑 */
  .product-table :deep(.status-column) {
    width: 60px !important;
    min-width: 60px !important;
    max-width: 60px !important;
  }

  /* 时间列优化 - 更紧凑 */
  .product-table :deep(.time-column) {
    width: 100px !important;
    min-width: 100px !important;
    max-width: 100px !important;
  }

  /* 操作列优化 - 更紧凑 */
  .product-table :deep(.action-column) {
    width: 100px !important;
    min-width: 100px !important;
    max-width: 100px !important;
    position: sticky;
    right: 0;
    background: var(--bg-primary);
    z-index: 10;
  }

  .product-table :deep(.el-table__header-cell) {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #fff;
  }

  /* 表格列移动端优化 */
  .product-table :deep(.el-table-column--selection) {
    width: 50px !important;
    min-width: 50px !important;
  }

  /* 产品名称单元格移动端优化 - 更紧凑 */
  .product-name-cell {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 4px;
    max-width: 180px;
    overflow: hidden;
  }

  .product-icon {
    font-size: 12px;
    flex-shrink: 0;
  }

  .product-name {
    font-size: 10px;
    line-height: 1.2;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    min-width: 0;
    max-width: 160px;
  }

  /* 时间单元格移动端优化 - 更紧凑 */
  .time-cell {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 3px;
    font-size: 9px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .time-cell .el-icon {
    font-size: 10px;
    flex-shrink: 0;
  }

  .time-cell span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 9px;
  }

  /* 操作按钮移动端优化 - 更紧凑 */
  .action-buttons.mobile-actions {
    display: flex;
    flex-direction: row;
    gap: 3px;
    justify-content: center;
    align-items: center;
    flex-wrap: nowrap;
    width: 100%;
    padding: 0;
  }

  .action-buttons.mobile-actions .action-btn {
    width: 28px;
    height: 28px;
    min-width: 28px;
    min-height: 28px;
    padding: 0;
    border-radius: 50%;
    margin: 0;
    flex-shrink: 0;
  }

  .action-buttons.mobile-actions .action-btn .el-icon {
    margin-right: 0;
    font-size: 12px;
  }

  .action-buttons.mobile-actions .action-btn.is-circle {
    width: 28px;
    height: 28px;
  }

  /* 确保操作按钮在固定列中正确显示 */
  .product-table :deep(.action-column .action-buttons) {
    justify-content: center;
    width: 100%;
    gap: 3px;
  }

  .product-table :deep(.action-column) {
    padding: 4px !important;
  }

  /* 标签移动端优化 - 更紧凑 */
  .product-table :deep(.el-tag) {
    font-size: 9px;
    padding: 1px 4px;
    line-height: 1.2;
    white-space: nowrap;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    height: auto;
    min-height: 18px;
  }

  /* 确保标签不会换行 */
  .product-table :deep(.el-tag span) {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
    font-size: 9px;
    line-height: 1.2;
  }

  /* 表格行触摸反馈优化 */
  .product-table :deep(.el-table__row) {
    -webkit-tap-highlight-color: rgba(0, 0, 0, 0.05);
    transition: background-color 0.2s;
  }

  .product-table :deep(.el-table__row:active) {
    background-color: #f0f2f5;
  }

  /* 按钮触摸反馈优化 */
  .action-btn,
  .add-button {
    -webkit-tap-highlight-color: rgba(0, 0, 0, 0.1);
    touch-action: manipulation;
  }

  .action-btn:active,
  .add-button:active {
    opacity: 0.8;
    transform: scale(0.98);
  }

  /* 加载状态移动端优化 */
  .product-table :deep(.el-loading-mask) {
    border-radius: 8px;
  }

  .product-table :deep(.el-loading-spinner) {
    margin-top: -25px;
  }

  .product-table :deep(.el-loading-text) {
    font-size: 14px;
    margin-top: 8px;
  }

  /* 表格固定列移动端优化 */
  .product-table :deep(.el-table__fixed),
  .product-table :deep(.el-table__fixed-right) {
    box-shadow: none;
  }

  /* 表格边框移动端优化 */
  .product-table :deep(.el-table) {
    border: 1px solid #ebeef5;
  }

  .product-table :deep(.el-table th),
  .product-table :deep(.el-table td) {
    border-right: 1px solid #ebeef5;
  }

  /* 操作栏标签移动端优化 */
  .action-right .el-tag {
    font-size: 13px;
    padding: 8px 12px;
  }
  
  /* 产品表单对话框移动端优化 */
  .product-form-dialog :deep(.el-dialog) {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    top: 0 !important;
    left: 0 !important;
    transform: none !important;
    max-height: 100vh;
    height: 100vh;
    border-radius: 0;
    display: flex;
    flex-direction: column;
  }

  .product-form-dialog :deep(.el-dialog__wrapper) {
    padding: 0;
  }
  
  .product-form-dialog :deep(.el-dialog__header) {
    padding: 16px;
    flex-shrink: 0;
    border-bottom: 1px solid #ebeef5;
  }

  .product-form-dialog :deep(.el-dialog__title) {
    font-size: 18px;
    font-weight: 600;
  }
  
  .product-form-dialog :deep(.el-dialog__body) {
    padding: 16px;
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .product-form-dialog :deep(.el-dialog__footer) {
    padding: 12px 16px;
    display: flex;
    flex-direction: row;
    gap: 12px;
    border-top: 1px solid #ebeef5;
    flex-shrink: 0;
  }
  
  .product-form-dialog :deep(.el-dialog__footer .el-button) {
    flex: 1;
    height: 48px;
    min-height: 48px;
    font-size: 16px;
    border-radius: 12px;
  }

  .product-form-dialog :deep(.el-dialog__headerbtn) {
    top: 16px;
    right: 16px;
    width: 44px;
    height: 44px;
    font-size: 20px;
  }
  
  /* 表单移动端优化 */
  .product-form {
    padding: 0;
  }

  .product-form :deep(.el-form-item) {
    margin-bottom: 24px;
  }

  .product-form :deep(.el-form-item__label) {
    width: 100% !important;
    text-align: left !important;
    margin-bottom: 8px !important;
    padding: 0 !important;
    font-size: 14px;
    font-weight: 600;
    color: #303133;
    line-height: 1.5;
  }
  
  .product-form :deep(.el-form-item__content) {
    width: 100% !important;
    margin-left: 0 !important;
    line-height: normal;
  }
  
  .product-form :deep(.el-input),
  .product-form :deep(.el-select),
  .product-form :deep(.el-input-number),
  .product-form :deep(.el-autocomplete) {
    width: 100% !important;
  }
  
  .product-form :deep(.el-input__wrapper) {
    min-height: 48px;
    font-size: 16px;
    border-radius: 8px;
  }

  .product-form :deep(.el-input__inner) {
    font-size: 16px;
    padding: 0 16px;
  }
  
  .product-form :deep(.el-select .el-input__wrapper) {
    min-height: 48px;
    font-size: 16px;
  }

  .product-form :deep(.el-select .el-input__inner) {
    font-size: 16px;
  }
  
  .product-form :deep(.el-input-number) {
    width: 100% !important;
  }
  
  .product-form :deep(.el-input-number .el-input__wrapper) {
    min-height: 48px;
    font-size: 16px;
  }

  .product-form :deep(.el-input-number .el-input__inner) {
    font-size: 16px;
  }

  .product-form :deep(.el-autocomplete .el-input__wrapper) {
    min-height: 48px;
    font-size: 16px;
  }

  .product-form :deep(.el-autocomplete .el-input__inner) {
    font-size: 16px;
  }
  
  /* 开关移动端优化 */
  .status-wrapper .el-switch {
    min-width: 50px;
    min-height: 28px;
  }

  .status-wrapper .el-switch :deep(.el-switch__core) {
    min-width: 50px;
    height: 28px;
  }

  .status-wrapper .el-switch :deep(.el-switch__action) {
    width: 24px;
    height: 24px;
  }
  
  /* 表单提示移动端优化 */
  .form-hint {
    font-size: 12px;
    padding: 8px 12px;
    line-height: 1.5;
    margin-top: 8px;
  }

  .form-hint .el-icon {
    font-size: 14px;
    flex-shrink: 0;
  }

  .form-hint span {
    flex: 1;
    word-break: break-word;
  }

  .product-name-wrapper {
    min-height: auto;
  }

  .form-hint-container {
    min-height: auto;
  }

  /* 日期选择器移动端优化 */
  .product-form :deep(.el-date-editor) {
    width: 100% !important;
  }

  .product-form :deep(.el-date-editor .el-input__wrapper) {
    min-height: 48px;
    font-size: 16px;
  }

  .product-form :deep(.el-date-editor .el-input__inner) {
    font-size: 16px;
  }

  /* 对话框底部按钮移动端优化 */
  .dialog-footer-buttons {
    width: 100%;
    gap: 12px;
  }

  .dialog-footer-buttons .el-button {
    flex: 1;
    height: 48px;
    min-height: 48px;
    font-size: 16px;
    border-radius: 12px;
  }

  /* 产品转移日期对话框移动端优化 */
  .el-dialog[aria-label="选择产品转移日期"] {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    max-height: 100vh;
    height: 100vh;
    border-radius: 0;
  }

  .el-dialog[aria-label="选择产品转移日期"] :deep(.el-dialog__body) {
    padding: 16px;
    max-height: calc(100vh - 140px);
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
  }
}
</style>
