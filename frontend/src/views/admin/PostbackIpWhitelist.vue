<template>
  <div class="ip-whitelist-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1>Postback IP 白名单管理</h1>
        <p class="header-description">
          管理允许接收 postback 数据的 IP 地址列表。只有白名单中的 IP 地址发送的 postback 数据才会被处理并记录。
        </p>
      </div>
      <div class="header-right">
        <el-button :icon="Plus" @click="handleCreate">
          添加 IP
        </el-button>
        <el-button type="primary" :icon="Plus" @click="handleBatchCreate">
          批量添加
        </el-button>
      </div>
    </div>

    <!-- 筛选控件 -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="IP地址">
          <el-input 
            v-model="searchForm.ip_address" 
            placeholder="输入IP地址（模糊搜索）" 
            clearable
            @keyup.enter="fetchList"
            style="width: 200px;"
          >
            <template #prefix>
              <el-icon :size="16"><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.is_active" placeholder="全部" clearable style="width: 150px;">
            <el-option label="启用" :value="true" />
            <el-option label="禁用" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchList" :loading="loading" :icon="Search">
            查询
          </el-button>
          <el-button @click="resetFilter" :icon="Refresh">
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="data-table-card" shadow="never">
      <template #header>
        <div class="table-header">
          <span>IP 白名单列表</span>
          <el-button 
            type="text" 
            :icon="Setting" 
            @click="columnSettingVisible = true"
            style="float: right;"
          >
            列设置
          </el-button>
        </div>
      </template>
      <el-table
        v-loading="loading"
        :data="whitelistItems"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column v-if="columnVisibility.id" prop="id" label="ID" width="80" align="center" />
        <el-table-column v-if="columnVisibility.ip_address" prop="ip_address" label="IP地址" min-width="180" show-overflow-tooltip>
          <template #default="scope">
            <el-tag type="primary" size="small">
              {{ scope.row.ip_address }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.description" prop="description" label="描述" min-width="200" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.description || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.is_active" prop="is_active" label="状态" width="100" align="center">
          <template #default="scope">
            <el-switch
              v-model="scope.row.is_active"
              @change="handleStatusChange(scope.row)"
              :active-text="scope.row.is_active ? '启用' : ''"
              :inactive-text="!scope.row.is_active ? '禁用' : ''"
              aria-label="切换状态"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.created_at" prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDateTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.updated_at" prop="updated_at" label="更新时间" width="180">
          <template #default="scope">
            {{ formatDateTime(scope.row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="scope">
            <el-button 
              type="primary" 
              link 
              size="small" 
              @click="handleEdit(scope.row)"
            >
              编辑
            </el-button>
            <el-button 
              type="danger" 
              link 
              size="small" 
              @click="handleDelete(scope.row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          :layout="isMobile ? 'total, prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
        />
      </div>
    </el-card>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      :width="isMobile ? '95%' : '600px'"
      :close-on-click-modal="false"
      :append-to-body="true"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="100px"
      >
        <el-form-item label="IP地址" prop="ip_address">
          <el-input 
            v-model="formData.ip_address" 
            placeholder="请输入IP地址（支持IPv4和IPv6）"
          />
          <div class="form-tip">例如：43.130.108.206</div>
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input 
            v-model="formData.description" 
            type="textarea"
            :rows="3"
            placeholder="请输入IP地址的描述或备注（可选）"
            maxlength="255"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch 
            v-model="formData.is_active"
            active-text="启用"
            inactive-text="禁用"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量添加对话框 -->
    <el-dialog
      v-model="batchDialogVisible"
      title="批量添加 IP"
      :width="isMobile ? '95%' : '700px'"
      :close-on-click-modal="false"
      :append-to-body="true"
    >
      <el-form
        ref="batchFormRef"
        :model="batchFormData"
        :rules="batchFormRules"
        label-width="100px"
      >
        <el-form-item label="IP地址列表" prop="ip_addresses_text">
          <el-input 
            v-model="batchFormData.ip_addresses_text" 
            type="textarea"
            :rows="10"
            placeholder="请输入IP地址，每行一个，或用逗号分隔&#10;例如：&#10;43.130.108.206&#10;192.168.1.1&#10;或者：43.130.108.206, 192.168.1.1, 10.0.0.1"
          />
          <div class="form-tip">
            支持换行或逗号分隔，每行/每个IP地址会自动验证格式。最多支持100个IP地址。
          </div>
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input 
            v-model="batchFormData.description" 
            type="textarea"
            :rows="3"
            placeholder="请输入IP地址的描述或备注（可选，将应用于所有IP）"
            maxlength="255"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch 
            v-model="batchFormData.is_active"
            active-text="启用"
            inactive-text="禁用"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleBatchSubmit" :loading="batchSubmitting">
          确定
        </el-button>
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
        <el-checkbox label="id" :disabled="true">ID（固定显示）</el-checkbox>
        <el-checkbox label="ip_address" :disabled="true">IP地址（固定显示）</el-checkbox>
        <el-checkbox label="description">描述</el-checkbox>
        <el-checkbox label="is_active">状态</el-checkbox>
        <el-checkbox label="created_at">创建时间</el-checkbox>
        <el-checkbox label="updated_at">更新时间</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue';
import { logger } from '../../utils/logger';
import { usePostbackIpWhitelistColumnVisibility } from '../../composables/usePostbackIpWhitelistColumnVisibility';
import { 
  ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem, 
  ElInput, ElSelect, ElOption, ElTag, ElDialog, ElIcon, ElMessage, ElMessageBox,
  ElSwitch, ElCheckboxGroup, ElCheckbox
} from 'element-plus';
import { Search, Refresh, Plus, Setting } from '@element-plus/icons-vue';
import { getIpWhitelist, createIpWhitelist, updateIpWhitelist, deleteIpWhitelist, batchCreateIpWhitelist } from '../../api/postback';
import { formatDateTime } from '../../utils/dateFormat';
import { useDevice } from '../../composables/useDevice';

// 设备检测
const { isMobile } = useDevice();

// 状态管理
const whitelistItems = ref([]);
const loading = ref(false);
const submitting = ref(false);
const batchSubmitting = ref(false);
const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility
} = usePostbackIpWhitelistColumnVisibility();

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
});

// 搜索表单
const searchForm = reactive({
  ip_address: '',
  is_active: null
});

// 对话框
const dialogVisible = ref(false);
const dialogTitle = ref('添加 IP');
const isEdit = ref(false);
const currentEditId = ref(null);
const formRef = ref(null);
const formData = reactive({
  ip_address: '',
  description: '',
  is_active: true
});

// 批量添加对话框
const batchDialogVisible = ref(false);
const batchFormRef = ref(null);
const batchFormData = reactive({
  ip_addresses_text: '',
  description: '',
  is_active: true
});

// IP地址格式验证函数
const validateIpAddress = (value) => {
  if (!value || !value.trim()) {
    return '请输入IP地址';
  }
  
  const trimmedValue = value.trim();
  
  // IPv4 验证：格式为 x.x.x.x，每个 x 是 0-255 的数字
  const ipv4Regex = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;
  if (ipv4Regex.test(trimmedValue)) {
    const parts = trimmedValue.split('.');
    // 检查每个段是否在 0-255 范围内
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      // 检查是否以0开头但不是单个0（如 01, 001 等无效）
      if (part.length > 1 && part.startsWith('0')) {
        return 'IPv4地址格式错误：不能有前导零（如 01, 001）';
      }
      const num = parseInt(part, 10);
      if (isNaN(num) || num < 0 || num > 255) {
        return 'IPv4地址的每个段必须在0-255范围内';
      }
    }
    return true; // IPv4 验证通过
  }
  
  // IPv6 验证：支持完整格式和简化格式
  // 完整格式：2001:0db8:85a3:0000:0000:8a2e:0370:7334
  // 简化格式：2001:db8:85a3::8a2e:370:7334 或 ::1 或 ::
  const ipv6Regex = /^(([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]+|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/;
  
  if (ipv6Regex.test(trimmedValue)) {
    return true; // IPv6 验证通过
  }
  
  return '请输入有效的IP地址格式（IPv4：如 192.168.1.1，IPv6：如 2001:db8::1）';
};

// 检查IP是否重复
const checkIpDuplicate = async (ipAddress, excludeId = null) => {
  if (!ipAddress || !ipAddress.trim()) {
    return false;
  }
  
  try {
    const trimmedIp = ipAddress.trim();
    const allItems = [];
    let page = 1;
    const pageSize = 100; // 最大允许的 page_size
    let hasMore = true;
    
    // 分页获取所有白名单记录
    while (hasMore) {
      const response = await getIpWhitelist({
        page: page,
        page_size: pageSize,
      });
      
      if (response.data && response.data.length > 0) {
        allItems.push(...response.data);
        
        // 检查是否还有更多记录
        const total = response.total || 0;
        if (allItems.length >= total || response.data.length < pageSize) {
          hasMore = false;
        } else {
          page++;
        }
      } else {
        hasMore = false;
      }
    }
    
    // 检查是否有完全匹配的IP（排除当前编辑的记录）
    if (allItems.length > 0) {
      const duplicate = allItems.find(item => {
        if (excludeId && item.id === excludeId) {
          return false; // 排除当前编辑的记录
        }
        // 精确匹配（去除空格后比较）
        return item.ip_address && item.ip_address.trim() === trimmedIp;
      });
      
      return !!duplicate;
    }
    
    return false;
  } catch (error) {
    // 如果检查失败，返回 false，让后端验证处理
    logger.error('检查IP重复失败:', error);
    return false;
  }
};

// 解析IP地址文本（支持换行和逗号分隔）
const parseIpAddresses = (text) => {
  if (!text || !text.trim()) {
    return [];
  }
  
  // 先按换行分割，再按逗号分割
  const lines = text.split(/\r?\n/);
  const ipList = [];
  
  for (const line of lines) {
    // 按逗号分割
    const parts = line.split(',');
    for (const part of parts) {
      const trimmed = part.trim();
      if (trimmed) {
        ipList.push(trimmed);
      }
    }
  }
  
  // 去重
  return [...new Set(ipList)];
};

// 批量表单验证规则
const batchFormRules = {
  ip_addresses_text: [
    { required: true, message: '请输入IP地址列表', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (!value || !value.trim()) {
          callback(new Error('请输入IP地址列表'));
          return;
        }
        
        const ipList = parseIpAddresses(value);
        
        if (ipList.length === 0) {
          callback(new Error('没有有效的IP地址'));
          return;
        }
        
        if (ipList.length > 100) {
          callback(new Error('一次最多只能添加100个IP地址'));
          return;
        }
        
        // 验证每个IP地址格式
        const invalidIps = [];
        for (const ip of ipList) {
          const formatResult = validateIpAddress(ip);
          if (formatResult !== true) {
            invalidIps.push(`${ip} (${formatResult})`);
          }
        }
        
        if (invalidIps.length > 0) {
          callback(new Error(`以下IP地址格式无效：\n${invalidIps.slice(0, 5).join('\n')}${invalidIps.length > 5 ? `\n... 还有 ${invalidIps.length - 5} 个` : ''}`));
          return;
        }
        
        callback();
      },
      trigger: 'blur'
    }
  ],
  description: [
    { max: 255, message: '描述不能超过255个字符', trigger: 'blur' }
  ]
};

// 表单验证规则
const formRules = {
  ip_address: [
    { required: true, message: '请输入IP地址', trigger: 'blur' },
    {
      validator: async (rule, value, callback) => {
        // 格式验证
        const formatResult = validateIpAddress(value);
        if (formatResult !== true) {
          callback(new Error(formatResult));
          return;
        }
        
        // 检查是否重复（仅在格式正确后检查）
        const trimmedValue = value.trim();
        const isDuplicate = await checkIpDuplicate(
          trimmedValue, 
          isEdit.value ? currentEditId.value : null
        );
        
        if (isDuplicate) {
          callback(new Error('该IP地址已存在于白名单中，不能重复添加'));
          return;
        }
        
        callback();
      },
      trigger: 'blur'
    }
  ],
  description: [
    { max: 255, message: '描述不能超过255个字符', trigger: 'blur' }
  ]
};

// 监听分页变化
watch(() => pagination.page, () => {
  fetchList();
});

watch(() => pagination.pageSize, () => {
  pagination.page = 1;
  fetchList();
});

// 获取列表
const fetchList = async () => {
  loading.value = true;
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...searchForm
    };
    
    // 移除空值
    Object.keys(params).forEach(key => {
      if (params[key] === '' || params[key] === null || params[key] === undefined) {
        delete params[key];
      }
    });

    const response = await getIpWhitelist(params);
    whitelistItems.value = response.data || [];
    pagination.total = response.total || 0;
  } catch (error) {
    // 错误已通过 handleError 处理
  } finally {
    loading.value = false;
  }
};

// 重置筛选
const resetFilter = () => {
  searchForm.ip_address = '';
  searchForm.is_active = null;
  pagination.page = 1;
  fetchList();
};

// 创建
const handleCreate = () => {
  isEdit.value = false;
  currentEditId.value = null;
  dialogTitle.value = '添加 IP';
  formData.ip_address = '';
  formData.description = '';
  formData.is_active = true;
  dialogVisible.value = true;
  // 清除表单验证
  if (formRef.value) {
    formRef.value.clearValidate();
  }
};

// 批量创建
const handleBatchCreate = () => {
  batchFormData.ip_addresses_text = '';
  batchFormData.description = '';
  batchFormData.is_active = true;
  batchDialogVisible.value = true;
  // 清除表单验证
  if (batchFormRef.value) {
    batchFormRef.value.clearValidate();
  }
};

// 批量提交
const handleBatchSubmit = async () => {
  if (!batchFormRef.value) return;
  
  try {
    await batchFormRef.value.validate();
    
    // 解析IP地址列表
    const ipList = parseIpAddresses(batchFormData.ip_addresses_text);
    
    if (ipList.length === 0) {
      ElMessage.error('没有有效的IP地址');
      return;
    }
    
    // 再次验证格式
    const invalidIps = [];
    for (const ip of ipList) {
      const formatResult = validateIpAddress(ip);
      if (formatResult !== true) {
        invalidIps.push(ip);
      }
    }
    
    if (invalidIps.length > 0) {
      ElMessage.error(`以下IP地址格式无效：${invalidIps.slice(0, 5).join(', ')}${invalidIps.length > 5 ? ` 等 ${invalidIps.length} 个` : ''}`);
      return;
    }
    
    batchSubmitting.value = true;
    
    try {
      const response = await batchCreateIpWhitelist({
        ip_addresses: ipList,
        description: batchFormData.description || null,
        is_active: batchFormData.is_active
      });
      
      const successCount = response.success_count || 0;
      const failedCount = response.failed_count || 0;
      const totalCount = response.total_count || 0;
      
      // 如果所有IP都失败（全部已存在）
      if (successCount === 0 && failedCount > 0) {
        const allDuplicates = response.failed_items && response.failed_items.every(
          item => item.error && item.error.includes('已存在于白名单中')
        );
        
        if (allDuplicates) {
          // 所有IP都已存在，使用信息提示而不是警告
          ElMessage.info({
            message: `所有 ${totalCount} 个IP地址都已存在于白名单中，无需重复添加`,
            duration: 5000,
            showClose: true
          });
        } else {
          // 有其他错误
          if (response.failed_items && response.failed_items.length > 0) {
            const failedDetails = response.failed_items.slice(0, 5).map(item => 
              `${item.ip_address}: ${item.error}`
            ).join('\n');
            ElMessage.warning({
              message: `批量添加失败：所有 ${totalCount} 个IP地址都无法添加\n失败详情：\n${failedDetails}${response.failed_items.length > 5 ? `\n... 还有 ${response.failed_items.length - 5} 个失败项` : ''}`,
              duration: 8000,
              showClose: true
            });
          } else {
            ElMessage.warning(`批量添加失败：所有 ${totalCount} 个IP地址都无法添加`);
          }
        }
      } else if (failedCount > 0) {
        // 部分成功部分失败
        let message = `批量添加完成：成功 ${successCount} 个，失败 ${failedCount} 个`;
        if (response.failed_items && response.failed_items.length > 0) {
          const failedDetails = response.failed_items.slice(0, 5).map(item => 
            `${item.ip_address}: ${item.error}`
          ).join('\n');
          ElMessage.warning({
            message: message + `\n失败详情：\n${failedDetails}${response.failed_items.length > 5 ? `\n... 还有 ${response.failed_items.length - 5} 个失败项` : ''}`,
            duration: 8000,
            showClose: true
          });
        } else {
          ElMessage.warning(message);
        }
      } else {
        // 全部成功
        ElMessage.success(`批量添加完成：成功添加 ${successCount} 个IP地址`);
      }
      
      batchDialogVisible.value = false;
      fetchList();
    } catch (error) {
      // 如果是批量创建的错误响应，尝试获取详细错误信息
      const errorDetail = error?.response?.data?.detail || error?.response?.data?.message || error?.message || '批量创建失败，请稍后重试';
      ElMessage.error(errorDetail);
      logger.error('批量创建IP白名单失败:', error);
    } finally {
      batchSubmitting.value = false;
    }
  } catch (error) {
    // 表单验证失败，错误信息已由验证规则显示
  }
};

// 编辑
const handleEdit = (row) => {
  isEdit.value = true;
  currentEditId.value = row.id;
  dialogTitle.value = '编辑 IP';
  formData.ip_address = row.ip_address;
  formData.description = row.description || '';
  formData.is_active = row.is_active;
  dialogVisible.value = true;
  // 清除表单验证
  if (formRef.value) {
    formRef.value.clearValidate();
  }
};

// 删除
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除 IP 地址 "${row.ip_address}" 吗？`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    
    try {
      await deleteIpWhitelist(row.id);
      ElMessage.success('删除成功');
      fetchList();
    } catch (error) {
      ElMessage.error('删除失败，请稍后重试');
    }
  } catch (error) {
    // 用户取消操作
  }
};

// 切换状态
const handleStatusChange = async (row) => {
  const originalState = row.is_active;
  try {
    await updateIpWhitelist(row.id, { is_active: row.is_active });
    fetchList();
  } catch (error) {
    // 恢复原状态
    row.is_active = originalState;
    logger.error('更新IP白名单状态失败:', error);
    ElMessage.error('状态更新失败');
  }
};

// 提交表单
const handleSubmit = async () => {
  if (!formRef.value) return;
  
  try {
    await formRef.value.validate();
    
    // 再次检查IP格式和重复（双重验证）
    const trimmedIp = formData.ip_address.trim();
    const formatResult = validateIpAddress(trimmedIp);
    if (formatResult !== true) {
      ElMessage.error(formatResult);
      return;
    }
    
    // 再次检查重复
    const isDuplicate = await checkIpDuplicate(
      trimmedIp,
      isEdit.value ? currentEditId.value : null
    );
    
    if (isDuplicate) {
      ElMessage.error('该IP地址已存在于白名单中，不能重复添加');
      return;
    }
    
    submitting.value = true;
    
    try {
      if (isEdit.value && currentEditId.value) {
        // 编辑模式
        await updateIpWhitelist(currentEditId.value, {
          ip_address: trimmedIp,
          description: formData.description,
          is_active: formData.is_active
        });
        ElMessage.success('更新成功');
      } else {
        // 创建模式
        await createIpWhitelist({
          ip_address: trimmedIp,
          description: formData.description,
          is_active: formData.is_active
        });
        ElMessage.success('创建成功');
      }
      
      dialogVisible.value = false;
      fetchList();
    } catch (error) {
      // 处理后端返回的错误信息
      const errorMessage = error?.response?.data?.detail || error?.message || 
        (isEdit.value ? '更新失败，请稍后重试' : '创建失败，请稍后重试');
      ElMessage.error(errorMessage);
    } finally {
      submitting.value = false;
    }
  } catch (error) {
    // 表单验证失败，错误信息已由验证规则显示
  }
};

// 初始化
onMounted(() => {
  // 加载列显示设置
  loadColumnVisibility();
  fetchList();
});
</script>

<style scoped>
.ip-whitelist-container {
  padding: var(--spacing-lg);
}

.page-header {
  margin-bottom: var(--spacing-lg);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.header-left h1 {
  margin: 0 0 var(--spacing-sm) 0;
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
}

.header-description {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.header-right {
  display: flex;
  gap: var(--spacing-md);
}

.filter-card {
  margin-bottom: var(--spacing-lg);
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
}

.data-table-card {
  margin-bottom: var(--spacing-lg);
}

.data-table-card :deep(.el-card__body) {
  padding: var(--spacing-xl);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.table-header {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-lg);
}

.pagination-container {
  margin-top: var(--spacing-lg);
  display: flex;
  justify-content: flex-end;
}

.form-tip {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  margin-top: var(--spacing-xs);
}

/* 移动端优化 */
@media (max-width: 767px) {
  .ip-whitelist-container {
    padding: var(--spacing-md);
  }

  .page-header {
    flex-direction: column;
    gap: var(--spacing-md);
  }

  .filter-form {
    flex-direction: column;
  }

  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .data-table-card :deep(.el-table) {
    min-width: 1000px;
    font-size: 12px;
  }

  .data-table-card :deep(.el-table__cell) {
    padding: 8px 4px;
  }
}
</style>
