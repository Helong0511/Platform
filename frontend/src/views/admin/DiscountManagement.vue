<template>
  <div class="discount-management">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Discount /></el-icon>
            <span class="header-title">扣量管理</span>
          </div>
          <el-button type="primary" :icon="Plus" @click="handleAdd">添加扣量配置</el-button>
        </div>
      </template>

      <!-- 搜索栏 -->
      <div class="search-bar">
        <el-select
          v-model="filterDiscountType"
          placeholder="请选择扣量类型"
          clearable
          style="width: 160px; min-width: 160px;"
          @change="handleSearch"
        >
          <el-option label="全部" :value="null" />
          <el-option label="offer" value="offer" />
          <el-option label="channel" value="channel" />
        </el-select>
        <el-select
          v-model="filterOffer"
          placeholder="请选择Offer"
          clearable
          filterable
          style="width: 180px; margin-left: 10px; min-width: 180px;"
          @change="handleSearch"
        >
          <el-option
            v-for="offer in offerList"
            :key="offer.id"
            :label="`${offer.id} - ${offer.offer_name}`"
            :value="offer.id"
          />
        </el-select>
        <el-select
          v-model="filterPublisher"
          placeholder="请选择渠道"
          clearable
          filterable
          style="width: 180px; margin-left: 10px; min-width: 180px;"
          @change="handleSearch"
        >
          <el-option
            v-for="pub in publisherList"
            :key="pub.id"
            :label="pub.publisher_name"
            :value="pub.id"
          />
        </el-select>
        <el-select
          v-model="filterActive"
          placeholder="请选择激活状态"
          clearable
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
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 20px; margin-bottom: 10px;">
        <span style="font-weight: 600;">扣量配置列表</span>
        <el-button 
          type="text" 
          :icon="Setting" 
          @click="columnSettingVisible = true"
        >
          列设置
        </el-button>
      </div>
      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        style="width: 100%;"
      >
        <el-table-column v-if="columnVisibility.discount_type" prop="discount_type" label="扣量类型" width="120" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.discount_type === 'offer' ? 'warning' : 'primary'">
              {{ scope.row.discount_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.offer_name" prop="offer_name" label="Offer" min-width="200" show-overflow-tooltip>
          <template #default="scope">
            <span v-if="scope.row.offer_name">{{ scope.row.offer_name }}</span>
            <span v-else class="text-info">渠道级别</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.publisher_name" prop="publisher_name" label="渠道" min-width="150" show-overflow-tooltip />
        <el-table-column v-if="columnVisibility.discount_ratio" prop="discount_ratio" label="扣量比例" width="120" align="right">
          <template #default="scope">
            <el-tag type="danger">{{ scope.row.discount_ratio }}%</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.is_active" prop="is_active" label="状态" width="100" align="center">
          <template #default="scope">
            <el-switch
              v-model="scope.row.is_active"
              @change="handleStatusChange(scope.row)"
              :active-text="scope.row.is_active ? '激活' : ''"
              :inactive-text="!scope.row.is_active ? '禁用' : ''"
              aria-label="切换状态"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.created_at" prop="created_at" label="创建时间" width="180">
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

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑扣量配置' : '添加扣量配置'"
      width="600px"
      :append-to-body="true"
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="120px"
      >
        <el-form-item label="扣量类型" prop="discount_type">
          <el-select 
            v-model="formData.discount_type" 
            style="width: 100%;" 
            @change="handleDiscountTypeChange"
          >
            <el-option label="offer（Offer级别）" value="offer" />
            <el-option label="channel（渠道级别）" value="channel" />
          </el-select>
        </el-form-item>

        <el-form-item
          v-if="formData.discount_type === 'offer'"
          label="Offer"
          prop="offer_id"
        >
          <el-select
            v-model="formData.offer_id"
            placeholder="请选择Offer"
            filterable
            style="width: 100%;"
          >
            <el-option
              v-for="offer in offerList"
              :key="offer.id"
              :label="`${offer.id} - ${offer.offer_name}`"
              :value="offer.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="渠道" prop="publisher_id">
          <el-select
            v-model="formData.publisher_id"
            placeholder="请选择渠道"
            filterable
            style="width: 100%;"
          >
            <el-option
              v-for="pub in publisherList"
              :key="pub.id"
              :label="pub.publisher_name"
              :value="pub.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="扣量比例" prop="discount_ratio">
          <el-input-number
            v-model="formData.discount_ratio"
            :min="0"
            :max="100"
            :precision="2"
            placeholder="0-100"
            style="width: 100%;"
          />
          <div class="form-hint">扣量比例（0-100），例如：10 表示扣量 10%</div>
        </el-form-item>

        <el-form-item label="激活" prop="is_active">
          <el-switch v-model="formData.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
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
        <el-checkbox label="discount_type">扣量类型</el-checkbox>
        <el-checkbox label="offer_name">Offer</el-checkbox>
        <el-checkbox label="publisher_name">渠道</el-checkbox>
        <el-checkbox label="discount_ratio">扣量比例</el-checkbox>
        <el-checkbox label="is_active">状态</el-checkbox>
        <el-checkbox label="created_at">创建时间</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus'
import { Plus, Search, Refresh, Edit, Delete, Discount, Setting } from '@element-plus/icons-vue'
import { getDiscounts, createDiscount, updateDiscount, deleteDiscount } from '@/api/discount'
import { getOffers } from '@/api/offer'
import { getPublishers } from '@/api/publisher'
import { logger } from '@/utils/logger'
import { formatDate } from '@/utils/date'

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const filterDiscountType = ref(null)
const filterOffer = ref(null)
const filterPublisher = ref(null)
const filterActive = ref(null)
const formRef = ref(null)

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const tableData = ref([])
const offerList = ref([])
const publisherList = ref([])
const columnSettingVisible = ref(false)

// 列显示状态（默认全部显示）
const getDefaultColumnVisibility = () => ({
  discount_type: true,
  offer_name: true,
  publisher_name: true,
  discount_ratio: true,
  is_active: true,
  created_at: true
})

const columnVisibility = reactive(getDefaultColumnVisibility())

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
    const saved = localStorage.getItem('discountManagement_columnVisibility')
    if (saved) {
      const savedVisibility = JSON.parse(saved)
      // 合并保存的设置和默认设置
      Object.assign(columnVisibility, getDefaultColumnVisibility(), savedVisibility)
    }
  } catch (error) {
    console.error('加载列显示设置失败:', error)
  }
}

// 保存列显示设置到localStorage
const saveColumnVisibility = () => {
  try {
    const toSave = {
      discount_type: columnVisibility.discount_type,
      offer_name: columnVisibility.offer_name,
      publisher_name: columnVisibility.publisher_name,
      discount_ratio: columnVisibility.discount_ratio,
      is_active: columnVisibility.is_active,
      created_at: columnVisibility.created_at
    }
    localStorage.setItem('discountManagement_columnVisibility', JSON.stringify(toSave))
    columnSettingVisible.value = false
    ElMessage.success('列显示设置已保存')
  } catch (error) {
    console.error('保存列显示设置失败:', error)
    ElMessage.error('保存设置失败')
  }
}

const formData = reactive({
  discount_type: 'offer',
  offer_id: null,
  publisher_id: null,
  discount_ratio: 0,
  is_active: true
})

const formRules = {
  discount_type: [
    { required: true, message: '请选择扣量类型', trigger: 'change' }
  ],
  publisher_id: [
    { required: true, message: '请选择渠道', trigger: 'change' }
  ],
  offer_id: [
    { required: true, message: '请选择Offer', trigger: 'change', validator: (rule, value, callback) => {
      if (formData.discount_type === 'offer' && !value) {
        callback(new Error('offer类型必须选择Offer'))
      } else {
        callback()
      }
    }}
  ],
  discount_ratio: [
    { required: true, message: '请输入扣量比例', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '扣量比例必须在0-100之间', trigger: 'blur' }
  ]
}

// 加载基础数据
const loadOffers = async () => {
  try {
    const response = await getOffers({ page: 1, page_size: 100 })
    // response已经是标准分页格式，直接使用data字段
    offerList.value = (response.data || []).slice().sort((a, b) => a.id - b.id)
  } catch (error) {
    logger.error('加载Offer列表失败:', error)
  }
}

const loadPublishers = async () => {
  try {
    const response = await getPublishers({ page: 1, page_size: 100 })
    // response已经是标准分页格式，直接使用data字段
    publisherList.value = response.data || []
  } catch (error) {
    logger.error('加载渠道列表失败:', error)
  }
}

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: Math.min(pagination.pageSize, 100),
      discount_type: filterDiscountType.value || undefined,
      offer_id: filterOffer.value || undefined,
      publisher_id: filterPublisher.value || undefined,
      is_active: filterActive.value !== null ? filterActive.value : undefined
    }
    const response = await getDiscounts(params)
    // response已经是标准分页格式，直接使用data和total字段
    tableData.value = response.data || []
    pagination.total = response.total || 0
  } catch (error) {
    logger.error('获取扣量配置列表失败:', error)
    ElMessage.error('获取数据失败')
  } finally {
    loading.value = false
  }
}

// 扣量类型改变
const handleDiscountTypeChange = () => {
  if (formData.discount_type !== 'offer') {
    formData.offer_id = null
  }
}

// 搜索
const handleSearch = () => {
  pagination.page = 1
  loadData()
}

// 重置
const handleReset = () => {
  filterDiscountType.value = null
  filterOffer.value = null
  filterPublisher.value = null
  filterActive.value = null
  pagination.page = 1
  loadData()
}

// 添加
const handleAdd = async () => {
  // 先获取最新的CSRF令牌（通过GET请求）
  try {
    await getDiscounts({ page: 1, page_size: 1 });
  } catch (error) {
    // 即使请求失败，也可能从响应头中获取到CSRF令牌
    console.debug('获取CSRF令牌失败，但可能已从响应头获取:', error);
  }

  isEdit.value = false
  Object.assign(formData, {
    discount_type: 'offer',
    offer_id: null,
    publisher_id: null,
    discount_ratio: 0,
    is_active: true
  })
  dialogVisible.value = true
}

// 编辑
const handleEdit = (row) => {
  isEdit.value = true
  Object.assign(formData, {
    id: row.id,
    discount_type: row.discount_type,
    offer_id: row.offer_id,
    publisher_id: row.publisher_id,
    discount_ratio: row.discount_ratio,
    is_active: row.is_active
  })
  dialogVisible.value = true
}

// 删除
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除此扣量配置吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await deleteDiscount(row.id)
    // deleteDiscount使用returnDataOnly: true，成功时直接返回数据，失败时抛出异常
    ElMessage.success('删除成功')
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      logger.error('删除扣量配置失败:', error)
      ElMessage.error('删除失败')
    }
  }
}

// 切换状态
const handleStatusChange = async (row) => {
  const originalState = row.is_active
  try {
    await updateDiscount(row.id, { is_active: row.is_active })
    loadData()
  } catch (error) {
    // 恢复原状态
    row.is_active = originalState
    
    logger.error('更新扣量配置状态失败:', error)
    
    // 检查是否是401未授权错误（token过期）
    if (error.response && error.response.status === 401) {
      return
    }
    
    // 检查是否是403错误（可能是CSRF token问题）
    if (error.response && error.response.status === 403 && error._handled) {
      return
    }
    
    // 其他错误显示具体错误信息
    const errorMsg = error.response?.data?.detail || error.response?.data?.message || error.message || '更新失败'
    ElMessage.error(errorMsg)
  }
}

// 提交
const handleSubmit = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    submitting.value = true
    try {
      if (isEdit.value) {
        // updateDiscount使用returnDataOnly: true，成功时直接返回数据，失败时抛出异常
        await updateDiscount(formData.id, formData)
      } else {
        // createDiscount使用returnDataOnly: true，成功时直接返回数据，失败时抛出异常
        await createDiscount(formData)
      }
      
      // 如果执行到这里，说明操作成功（失败会抛出异常）
      ElMessage.success(isEdit.value ? '更新成功' : '创建成功')
      dialogVisible.value = false
      loadData()
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

// 分页
const handleSizeChange = (size) => {
  pagination.pageSize = size;
  pagination.page = 1;  // 分页大小变化时重置到第一页
  loadData()
}

const handlePageChange = (page) => {
  pagination.page = page;
  loadData()
}

onMounted(() => {
  loadColumnVisibility()
  loadOffers()
  loadPublishers()
  loadData()
})
</script>

<style scoped>
.discount-management {
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

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.text-info {
  color: #909399;
  font-style: italic;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}
</style>

