<template>
  <div class="publisher-management">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Connection /></el-icon>
            <span class="header-title">渠道管理</span>
          </div>
          <el-button type="primary" :icon="Plus" @click="handleAdd">添加渠道</el-button>
        </div>
      </template>

      <!-- 搜索栏 -->
      <div class="search-bar">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索渠道名称或ID"
          clearable
          style="width: 300px;"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select
          v-model="filterActive"
          placeholder="请选择激活状态"
          clearable
          popper-class="select-dropdown"
          :teleported="true"
          style="width: 160px; margin-left: 10px; min-width: 160px;"
          @change="handleSearch"
        >
          <el-option label="全部" :value="null" />
          <el-option label="激活" :value="true" />
          <el-option label="禁用" :value="false" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="handleSearch" style="margin-left: 10px;">搜索</el-button>
        <el-button :icon="Refresh" @click="handleReset">重置</el-button>
      </div>

      <!-- 表格 -->
      <div class="table-wrapper">
        <el-table
          v-loading="loading"
          :data="tableData"
          stripe
          style="width: 100%; margin-top: 20px;"
        >
        <el-table-column prop="id" label="渠道ID" width="120" />
        <el-table-column prop="publisher_name" label="渠道名称" min-width="200" />
        <el-table-column prop="client_name" label="关联客户" min-width="150" show-overflow-tooltip>
          <template #default="scope">
            <span>{{ scope.row.client_name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="80" />
        <el-table-column prop="price_discount" label="价格折扣" width="120" align="center">
          <template #default="scope">
            <el-tag v-if="scope.row.price_discount > 0" type="info">{{ scope.row.price_discount }}%</el-tag>
            <span v-else style="color: #909399;">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="postback_url" label="Postback URL" min-width="400" show-overflow-tooltip>
          <template #default="scope">
            <span>{{ scope.row.postback_url || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="postback_method" label="Postback方法" width="150" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.postback_method === 'POST' ? 'success' : 'info'">
              {{ scope.row.postback_method || 'GET' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="active_advertiser_count" label="活跃广告主数" width="140" align="center" />
        <el-table-column prop="is_active" label="状态" width="100" align="center">
          <template #default="scope">
            <el-switch
              v-model="scope.row.is_active"
              @change="handleStatusChange(scope.row)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="scope">
            <el-button type="primary" link :icon="Edit" @click="handleEdit(scope.row)">编辑</el-button>
            <el-button type="danger" link :icon="Delete" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      </div>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          :max-page-size="100"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑渠道' : '添加渠道'"
      width="600px"
      :append-to-body="true"
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="100px"
      >
        <el-form-item label="渠道名称" prop="publisher_name">
          <el-input v-model="formData.publisher_name" placeholder="请输入渠道名称" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="formData.email" placeholder="请输入邮箱（可选）" />
        </el-form-item>
        <el-form-item label="价格折扣" prop="price_discount">
          <el-input-number
            v-model="formData.price_discount"
            :min="0"
            :max="100"
            :precision="2"
            placeholder="0-100"
            style="width: 100%;"
          />
          <div class="form-hint">
            <strong>价格折扣说明：</strong>渠道级别的价格折扣比例（0-100），用于计算给渠道的最终金额（affiliate_payout）。
            <br>
            <span style="color: #E6A23C;">
              <el-icon><Warning /></el-icon>
              <strong>注意：</strong>此字段为旧价格折扣系统，建议使用"扣减配置管理"页面配置更灵活的扣减规则（支持扣量和扣金额）。
            </span>
          </div>
        </el-form-item>
        <el-form-item label="Postback URL" prop="postback_url">
          <el-input
            v-model="formData.postback_url"
            type="textarea"
            :rows="5"
            placeholder="Postback URL（可选），支持占位符变量，例如：https://example.com/postback?click_id={click_id}&payout={payout}"
          />
          <div class="form-hint">
            <el-link type="primary" @click="showPlaceholderHelp = !showPlaceholderHelp" style="font-size: 12px;">
              <el-icon><InfoFilled /></el-icon>
              {{ showPlaceholderHelp ? '隐藏' : '查看' }}支持的占位符变量
            </el-link>
          </div>
          <el-collapse-transition>
            <div v-show="showPlaceholderHelp" class="placeholder-help">
              <div class="placeholder-help-title">支持的占位符变量：</div>
              <div class="placeholder-help-content">
                <div class="placeholder-group">
                  <div class="placeholder-group-title">转化记录字段：</div>
                  <div class="placeholder-list">
                    <div v-for="(desc, varName) in placeholderDescriptions.conversion" :key="varName" class="placeholder-item">
                      <code>{{ '{' + varName + '}' }}</code>
                      <span class="placeholder-desc">{{ desc }}</span>
                    </div>
                  </div>
                </div>
                <div class="placeholder-group">
                  <div class="placeholder-group-title">点击记录字段：</div>
                  <div class="placeholder-list">
                    <div v-for="(desc, varName) in placeholderDescriptions.click" :key="varName" class="placeholder-item">
                      <code>{{ '{' + varName + '}' }}</code>
                      <span class="placeholder-desc">{{ desc }}</span>
                    </div>
                  </div>
                </div>
                <div class="placeholder-group">
                  <div class="placeholder-group-title">Offer 字段：</div>
                  <div class="placeholder-list">
                    <div v-for="(desc, varName) in placeholderDescriptions.offer" :key="varName" class="placeholder-item">
                      <code>{{ '{' + varName + '}' }}</code>
                      <span class="placeholder-desc">{{ desc }}</span>
                    </div>
                  </div>
                </div>
                <div class="placeholder-group">
                  <div class="placeholder-group-title">渠道字段：</div>
                  <div class="placeholder-list">
                    <div v-for="(desc, varName) in placeholderDescriptions.publisher" :key="varName" class="placeholder-item">
                      <code>{{ '{' + varName + '}' }}</code>
                      <span class="placeholder-desc">{{ desc }}</span>
                    </div>
                  </div>
                </div>
                <div class="placeholder-group">
                  <div class="placeholder-group-title">广告主字段：</div>
                  <div class="placeholder-list">
                    <div v-for="(desc, varName) in placeholderDescriptions.advertiser" :key="varName" class="placeholder-item">
                      <code>{{ '{' + varName + '}' }}</code>
                      <span class="placeholder-desc">{{ desc }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </el-collapse-transition>
        </el-form-item>
        <el-form-item label="Postback方法" prop="postback_method">
          <el-select
            v-model="formData.postback_method"
            popper-class="select-dropdown"
            :teleported="true"
            style="width: 100%;"
          >
            <el-option label="GET" value="GET" />
            <el-option label="POST" value="POST" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联客户" prop="client_id">
          <el-select
            v-model="formData.client_id"
            placeholder="请选择客户（可选）"
            clearable
            filterable
            popper-class="select-dropdown"
            :teleported="true"
            style="width: 100%;"
          >
            <el-option
              v-for="client in clientList"
              :key="client.id"
              :label="client.user_full_name || client.company_name"
              :value="client.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch v-model="formData.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Refresh, Edit, Delete, Connection, InfoFilled, Warning } from '@element-plus/icons-vue'
import { getPublishers, createPublisher, updatePublisher, deletePublisher } from '@/api/publisher'
import { getClientList } from '@/api/client'
import { logger } from '@/utils/logger'
import { formatDate } from '@/utils/date'

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const searchKeyword = ref('')
const filterActive = ref(null)
const formRef = ref(null)
const showPlaceholderHelp = ref(false)

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const tableData = ref([])
const clientList = ref([])

const formData = reactive({
  publisher_name: '',
  email: '',
  price_discount: 0,
  postback_url: '',
  postback_method: 'GET',
  client_id: null,
  is_active: true
})

// 占位符变量中文说明
const placeholderDescriptions = {
  conversion: {
    'conversion_id': '转化ID（唯一标识）',
    'platform': '平台名称',
    'event_name': '事件名称',
    'event_value': '事件值',
    'payout': '支付金额',
    'devad_id': '开发者广告ID',
    'os': '操作系统',
    'carrier': '运营商',
    'ip': 'IP地址',
    'gid': 'GID',
    'product_id': '产品ID',
    'client_id': '客户ID',
    'click_id': '点击ID',
    'click_time': '点击时间（ISO格式）',
    'conversion_status': '转化状态',
    'timestamp': '时间戳（ISO格式）',
    'created_at': '创建时间（ISO格式）'
  },
  click: {
    'click_offer_id': '点击关联的Offer ID',
    'click_publisher_id': '点击关联的渠道ID',
    'click_advertiser_id': '点击关联的广告主ID',
    'click_ip': '点击IP地址',
    'click_device': '点击设备信息',
    'click_country': '点击国家',
    'click_user_agent': '点击User Agent',
    'click_referer': '点击来源页面'
  },
  offer: {
    'offer_id': 'Offer ID',
    'offer_name': 'Offer名称',
    'advertiser_offer_id': '广告主Offer ID',
    'offer_advertiser_id': 'Offer关联的广告主ID',
    'offer_payout': 'Offer支付金额',
    'affiliate_payout': '渠道支付金额',
    'offer_country': 'Offer国家',
    'offer_category': 'Offer分类',
    'offer_type': 'Offer类型',
    'offer_status': 'Offer状态'
  },
  publisher: {
    'publisher_id': '渠道ID',
    'channel_id': '渠道ID（别名）',
    'publisher_name': '渠道名称',
    'publisher_email': '渠道邮箱'
  },
  advertiser: {
    'advertiser_id': '广告主ID',
    'advertiser_name': '广告主名称',
    'advertiser_email': '广告主邮箱'
  }
}

// CPL 系统支持的占位符变量列表
const SUPPORTED_PLACEHOLDERS = new Set([
  // PostbackConversion 直接字段
  'conversion_id', 'platform', 'event_name', 'event_value', 'payout',
  'devad_id', 'os', 'carrier', 'ip', 'gid', 'product_id', 'client_id',
  'click_id', 'click_time', 'conversion_status', 'timestamp', 'created_at',
  // Click 关联字段
  'click_offer_id', 'click_publisher_id', 'click_advertiser_id', 'click_ip',
  'click_device', 'click_country', 'click_user_agent', 'click_referer',
  // Offer 关联字段
  'offer_id', 'offer_name', 'advertiser_offer_id', 'offer_advertiser_id',
  'offer_payout', 'affiliate_payout', 'offer_country', 'offer_category',
  'offer_type', 'offer_status',
  // Publisher 关联字段
  'publisher_id', 'channel_id', 'publisher_name', 'publisher_email',
  // Advertiser 关联字段
  'advertiser_id', 'advertiser_name', 'advertiser_email',
  // 支持的别名
  'clickid', 'clickId', 'clk_id', 'cid',
  'conversionId', 'conv_id',
  'publisherId', 'channelId', 'offerId',
  'eventName', 'eventId', 'event_id',
])

// 别名映射
const PLACEHOLDER_ALIAS_MAP = {
  'clickid': 'click_id',
  'clickId': 'click_id',
  'clk_id': 'click_id',
  'cid': 'click_id',
  'conversionId': 'conversion_id',
  'conv_id': 'conversion_id',
  'publisherId': 'publisher_id',
  'channelId': 'channel_id',
  'offerId': 'offer_id',
  'eventName': 'event_name',
  'eventId': 'event_name',
  'event_id': 'event_name',
}

// 规范化占位符名称
const normalizePlaceholder = (placeholder) => {
  const normalized = placeholder.toLowerCase()
  if (normalized in PLACEHOLDER_ALIAS_MAP) {
    return PLACEHOLDER_ALIAS_MAP[normalized]
  }
  // 将驼峰命名转换为下划线命名
  return placeholder.replace(/([A-Z])/g, '_$1').toLowerCase()
}

// 验证 Postback URL 占位符
const validatePostbackUrlPlaceholders = (rule, value, callback) => {
  if (!value || !value.trim()) {
    callback()
    return
  }
  
  // 使用正则表达式查找所有占位符 {变量名}
  const pattern = /\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g
  const placeholders = []
  let match
  while ((match = pattern.exec(value)) !== null) {
    placeholders.push(match[1])
  }
  
  if (placeholders.length === 0) {
    callback()
    return
  }
  
  // 检查每个占位符是否在支持的列表中
  const invalidPlaceholders = []
  for (const placeholder of placeholders) {
    // 检查原始占位符是否在支持的列表中（支持别名）
    if (SUPPORTED_PLACEHOLDERS.has(placeholder)) {
      continue
    }
    
    // 规范化占位符名称
    const normalized = normalizePlaceholder(placeholder)
    
    // 检查规范化后的名称是否在支持的列表中
    if (!SUPPORTED_PLACEHOLDERS.has(normalized)) {
      invalidPlaceholders.push(placeholder)
    }
  }
  
  if (invalidPlaceholders.length > 0) {
    const invalidList = invalidPlaceholders.map(p => `{${p}}`).join(', ')
    callback(new Error(`Postback URL 中包含不支持的占位符: ${invalidList}。请使用 CPL 系统支持的变量。`))
  } else {
    callback()
  }
}

const formRules = {
  publisher_name: [
    { required: true, message: '请输入渠道名称', trigger: 'blur' }
  ],
  price_discount: [
    { required: true, message: '请输入价格折扣', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '价格折扣必须在0-100之间', trigger: 'blur' }
  ],
  postback_url: [
    { validator: validatePostbackUrlPlaceholders, trigger: 'blur' }
  ]
}

// 加载客户列表（分页加载所有客户）
const loadClients = async () => {
  try {
    clientList.value = []
    let page = 1
    let hasMore = true
    
    while (hasMore) {
      const response = await getClientList({ page, page_size: 100 })
      if (response.code === 200) {
        const clients = response.data || []
        clientList.value.push(...clients)
        
        // 如果返回的数据少于 page_size，说明已经是最后一页
        if (clients.length < 100) {
          hasMore = false
        } else {
          page++
        }
      } else {
        hasMore = false
      }
    }
  } catch (error) {
    logger.error('获取客户列表失败:', error)
  }
}

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    // 限制 page_size 最大值为 100
    const pageSize = Math.min(pagination.pageSize, 100)
    const params = {
      page: pagination.page,
      page_size: pageSize,
      search: searchKeyword.value || undefined,
      is_active: filterActive.value !== null ? filterActive.value : undefined
    }
    const response = await getPublishers(params)
    if (response.code === 200) {
      tableData.value = response.data || []
      pagination.total = response.total || 0
    } else {
      ElMessage.error(response.message || '获取数据失败')
    }
  } catch (error) {
    logger.error('获取渠道列表失败:', error)
    ElMessage.error('获取数据失败')
  } finally {
    loading.value = false
  }
}

// 搜索
const handleSearch = () => {
  pagination.page = 1
  loadData()
}

// 重置
const handleReset = () => {
  searchKeyword.value = ''
  filterActive.value = null
  pagination.page = 1
  loadData()
}

// 添加
const handleAdd = () => {
  isEdit.value = false
  Object.assign(formData, {
    publisher_name: '',
    email: '',
    price_discount: 0,
    postback_url: '',
    postback_method: 'GET',
    client_id: null,
    is_active: true
  })
  dialogVisible.value = true
}

// 编辑
const handleEdit = (row) => {
  isEdit.value = true
  Object.assign(formData, {
    id: row.id,
    publisher_name: row.publisher_name,
    email: row.email || '',
    price_discount: row.price_discount || 0,
    postback_url: row.postback_url || '',
    postback_method: row.postback_method || 'GET',
    client_id: row.client_id || null,
    is_active: row.is_active
  })
  dialogVisible.value = true
}

// 删除
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除渠道 "${row.publisher_name}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const response = await deletePublisher(row.id)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      loadData()
    } else {
      ElMessage.error(response.message || '删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      logger.error('删除渠道失败:', error)
      ElMessage.error('删除失败')
    }
  }
}

// 提交
const handleSubmit = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    submitting.value = true
    try {
      let response
      if (isEdit.value) {
        response = await updatePublisher(formData.id, formData)
      } else {
        response = await createPublisher(formData)
      }
      
      if (response.code === 200) {
        ElMessage.success(isEdit.value ? '更新成功' : '创建成功')
        dialogVisible.value = false
        loadData()
      } else {
        ElMessage.error(response.message || '操作失败')
      }
    } catch (error) {
      logger.error('提交失败:', error)
      
      // 检查是否是401未授权错误（token过期）
      // 如果是401错误，axios拦截器已经处理了（清除认证信息并跳转到登录页）
      // 这里不需要重复显示错误信息，避免干扰用户体验
      if (error.response && error.response.status === 401) {
        // 401错误已被axios拦截器处理，直接返回，不显示"操作失败"
        return
      }
      
      // 检查是否是403错误（可能是CSRF token问题）
      // 403错误也可能已被axios拦截器处理（自动重试）
      if (error.response && error.response.status === 403) {
        // 如果错误已被处理（标记了_handled），不显示错误信息
        if (error._handled) {
          return
        }
      }
      
      // 其他错误显示具体错误信息
      const errorMsg = error.response?.data?.detail || error.response?.data?.message || error.message || '操作失败'
      ElMessage.error(errorMsg)
    } finally {
      submitting.value = false
    }
  })
}

// 对话框关闭
const handleDialogClose = () => {
  formRef.value?.resetFields()
}

// 状态切换
const handleStatusChange = async (row) => {
  try {
    const response = await updatePublisher(row.id, {
      is_active: row.is_active
    })
    if (response.code === 200) {
      ElMessage.success('状态更新成功')
    } else {
      // 如果更新失败，恢复原状态
      row.is_active = !row.is_active
      ElMessage.error(response.message || '状态更新失败')
    }
  } catch (error) {
    // 如果更新失败，恢复原状态
    row.is_active = !row.is_active
    logger.error('状态更新失败:', error)
    ElMessage.error('状态更新失败')
  }
}

// 分页
const handleSizeChange = () => {
  loadData()
}

const handlePageChange = () => {
  loadData()
}

onMounted(() => {
  loadClients()
  loadData()
})
</script>

<style scoped>
.publisher-management {
  padding: 20px;
}

.page-card {
  min-height: calc(100vh - 100px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-icon {
  font-size: 20px;
  color: #409eff;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
}

.search-bar {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 10px;
}

/* 确保输入框和下拉框文字不被遮盖 */
.search-bar :deep(.el-input__wrapper) {
  padding-right: 30px; /* 为清除按钮留出空间 */
}

.search-bar :deep(.el-select .el-input__wrapper) {
  padding-right: 30px; /* 为清除按钮和下拉箭头留出空间 */
}

.search-bar :deep(.el-input__inner),
.search-bar :deep(.el-select__input) {
  padding-right: 8px; /* 文字与清除按钮之间的间距 */
  text-overflow: ellipsis;
  overflow: hidden;
  white-space: nowrap;
}

/* 确保清除按钮不遮挡文字 */
.search-bar :deep(.el-input__suffix) {
  right: 8px;
}

.search-bar :deep(.el-select .el-input__suffix) {
  right: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.table-wrapper {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.table-wrapper :deep(.el-table) {
  min-width: 1000px;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .publisher-management {
    padding: 10px;
  }

  .search-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .search-bar > * {
    width: 100% !important;
    margin-left: 0 !important;
  }

  .table-wrapper :deep(.el-table) {
    min-width: 900px;
    font-size: 12px;
  }

  .table-wrapper :deep(.el-table__cell) {
    padding: 8px 4px;
  }
}

.placeholder-help {
  margin-top: 10px;
  padding: 12px;
  background-color: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  font-size: 12px;
}

.placeholder-help-title {
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}

.placeholder-help-content {
  max-height: 400px;
  overflow-y: auto;
}

.placeholder-group {
  margin-bottom: 15px;
}

.placeholder-group:last-child {
  margin-bottom: 0;
}

.placeholder-group-title {
  font-weight: 600;
  color: #409eff;
  margin-bottom: 8px;
  font-size: 13px;
}

.placeholder-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 8px;
}

.placeholder-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.placeholder-item code {
  background-color: #f0f2f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: #e6a23c;
  white-space: nowrap;
  min-width: 120px;
}

.placeholder-desc {
  color: #606266;
  font-size: 12px;
}

@media (max-width: 767px) {
  .placeholder-list {
    grid-template-columns: 1fr;
  }
}
</style>

