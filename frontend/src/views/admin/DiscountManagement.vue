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
          placeholder="扣量类型"
          clearable
          style="width: 180px;"
          @change="handleSearch"
        >
          <el-option label="全部" :value="null" />
          <el-option label="offer" value="offer" />
          <el-option label="channel" value="channel" />
        </el-select>
        <el-select
          v-model="filterOffer"
          placeholder="Offer"
          clearable
          filterable
          style="width: 200px; margin-left: 10px;"
          @change="handleSearch"
        >
          <el-option
            v-for="offer in offerList"
            :key="offer.id"
            :label="offer.offer_name"
            :value="offer.id"
          />
        </el-select>
        <el-select
          v-model="filterPublisher"
          placeholder="渠道"
          clearable
          filterable
          style="width: 200px; margin-left: 10px;"
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
          placeholder="激活状态"
          clearable
          style="width: 150px; margin-left: 10px;"
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
      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        style="width: 100%; margin-top: 20px;"
      >
        <el-table-column prop="discount_type" label="扣量类型" width="120">
          <template #default="scope">
            <el-tag :type="scope.row.discount_type === 'offer' ? 'warning' : 'primary'">
              {{ scope.row.discount_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="offer_name" label="Offer" min-width="200">
          <template #default="scope">
            <span v-if="scope.row.offer_name">{{ scope.row.offer_name }}</span>
            <span v-else class="text-info">渠道级别</span>
          </template>
        </el-table-column>
        <el-table-column prop="publisher_name" label="渠道" min-width="150" />
        <el-table-column prop="discount_ratio" label="扣量比例" width="120" align="right">
          <template #default="scope">
            <el-tag type="danger">{{ scope.row.discount_ratio }}%</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="100" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.is_active ? 'success' : 'danger'">
              {{ scope.row.is_active ? '激活' : '禁用' }}
            </el-tag>
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
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="120px"
      >
        <el-form-item label="扣量类型" prop="discount_type">
          <el-select v-model="formData.discount_type" style="width: 100%;" @change="handleDiscountTypeChange">
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
              :label="offer.offer_name"
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Refresh, Edit, Delete, Discount } from '@element-plus/icons-vue'
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
    if (response.code === 200) {
      offerList.value = response.data.data || []
    }
  } catch (error) {
    logger.error('加载Offer列表失败:', error)
  }
}

const loadPublishers = async () => {
  try {
    const response = await getPublishers({ page: 1, page_size: 1000 })
    if (response.code === 200) {
      publisherList.value = response.data.data || []
    }
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
    if (response.code === 200) {
      tableData.value = response.data.data || []
      pagination.total = response.data.total || 0
    } else {
      ElMessage.error(response.message || '获取数据失败')
    }
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
const handleAdd = () => {
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
    
    const response = await deleteDiscount(row.id)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      loadData()
    } else {
      ElMessage.error(response.message || '删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      logger.error('删除扣量配置失败:', error)
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
        response = await updateDiscount(formData.id, formData)
      } else {
        response = await createDiscount(formData)
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
      ElMessage.error('操作失败')
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
const handleSizeChange = () => {
  loadData()
}

const handlePageChange = () => {
  loadData()
}

onMounted(() => {
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

