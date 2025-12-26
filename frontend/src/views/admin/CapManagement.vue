<template>
  <div class="cap-management">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Switch /></el-icon>
            <span class="header-title">Cap管理</span>
          </div>
          <el-button type="primary" :icon="Plus" @click="handleAdd">添加Cap配置</el-button>
        </div>
      </template>

      <!-- 搜索栏 -->
      <div class="search-bar">
        <el-select
          v-model="filterCapType"
          placeholder="请选择Cap类型"
          clearable
          style="width: 160px; min-width: 160px;"
          @change="handleSearch"
        >
          <el-option label="全部" :value="null" />
          <el-option label="advertiser_offer" value="advertiser_offer" />
          <el-option label="offer" value="offer" />
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
            :label="offer.offer_name"
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
      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        style="width: 100%; margin-top: 20px;"
      >
        <el-table-column prop="cap_type" label="Cap类型" width="150">
          <template #default="scope">
            <el-tag :type="scope.row.cap_type === 'advertiser_offer' ? 'warning' : 'primary'">
              {{ scope.row.cap_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="offer_name" label="Offer" min-width="200" />
        <el-table-column prop="advertiser_name" label="广告主" width="150">
          <template #default="scope">
            <span v-if="scope.row.advertiser_name">{{ scope.row.advertiser_name }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="publisher_name" label="渠道" width="150">
          <template #default="scope">
            <span v-if="scope.row.publisher_name">{{ scope.row.publisher_name }}</span>
            <span v-else class="text-info">全部渠道</span>
          </template>
        </el-table-column>
        <el-table-column prop="daily_cap" label="每日Cap" width="120" align="right">
          <template #default="scope">
            <span v-if="scope.row.daily_cap">{{ scope.row.daily_cap }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="current_daily_count" label="当前每日" width="120" align="right">
          <template #default="scope">
            <el-tag :type="scope.row.daily_cap && scope.row.current_daily_count >= scope.row.daily_cap ? 'danger' : 'success'">
              {{ scope.row.current_daily_count }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_cap" label="总Cap" width="120" align="right">
          <template #default="scope">
            <span v-if="scope.row.total_cap">{{ scope.row.total_cap }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="current_total_count" label="当前总数" width="120" align="right">
          <template #default="scope">
            <el-tag :type="scope.row.total_cap && scope.row.current_total_count >= scope.row.total_cap ? 'danger' : 'success'">
              {{ scope.row.current_total_count }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="100" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.is_active ? 'success' : 'danger'">
              {{ scope.row.is_active ? '激活' : '禁用' }}
            </el-tag>
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
      :title="isEdit ? '编辑Cap配置' : '添加Cap配置'"
      width="700px"
      :append-to-body="true"
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="120px"
      >
        <el-form-item label="Cap类型" prop="cap_type">
          <el-select 
            v-model="formData.cap_type" 
            style="width: 100%;" 
            @change="handleCapTypeChange"
          >
            <el-option label="advertiser_offer" value="advertiser_offer" />
            <el-option label="offer" value="offer" />
          </el-select>
        </el-form-item>
        
        <el-form-item
          v-if="formData.cap_type === 'advertiser_offer'"
          label="广告主"
          prop="advertiser_id"
        >
          <el-select
            v-model="formData.advertiser_id"
            placeholder="请选择广告主"
            filterable
            style="width: 100%;"
          >
            <el-option
              v-for="adv in advertiserList"
              :key="adv.id"
              :label="adv.advertiser_name"
              :value="adv.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="Offer" prop="offer_id">
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
            placeholder="请选择渠道（留空表示所有渠道）"
            clearable
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

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="每日Cap" prop="daily_cap">
              <el-input-number
                v-model="formData.daily_cap"
                :min="0"
                placeholder="每日Cap（可选）"
                style="width: 100%;"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="总Cap" prop="total_cap">
              <el-input-number
                v-model="formData.total_cap"
                :min="0"
                placeholder="总Cap（可选）"
                style="width: 100%;"
              />
            </el-form-item>
          </el-col>
        </el-row>

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
import { Plus, Search, Refresh, Edit, Delete, Switch } from '@element-plus/icons-vue'
import { getCaps, createCap, updateCap, deleteCap } from '@/api/cap'
import { getOffers } from '@/api/offer'
import { getAdvertisers } from '@/api/advertiser'
import { getPublishers } from '@/api/publisher'
import { logger } from '@/utils/logger'

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const filterCapType = ref(null)
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
const advertiserList = ref([])
const publisherList = ref([])

const formData = reactive({
  cap_type: 'offer',
  advertiser_id: null,
  offer_id: null,
  publisher_id: null,
  daily_cap: null,
  total_cap: null,
  is_active: true
})

const formRules = {
  cap_type: [
    { required: true, message: '请选择Cap类型', trigger: 'change' }
  ],
  offer_id: [
    { required: true, message: '请选择Offer', trigger: 'change' }
  ],
  advertiser_id: [
    { required: true, message: '请选择广告主', trigger: 'change', validator: (rule, value, callback) => {
      if (formData.cap_type === 'advertiser_offer' && !value) {
        callback(new Error('advertiser_offer类型必须选择广告主'))
      } else {
        callback()
      }
    }}
  ]
}

// 加载基础数据
const loadOffers = async () => {
  try {
    const response = await getOffers({ page: 1, page_size: 100 })
    if (response.code === 200) {
      offerList.value = response.data || []
    }
  } catch (error) {
    logger.error('加载Offer列表失败:', error)
  }
}

const loadAdvertisers = async () => {
  try {
    const response = await getAdvertisers({ page: 1, page_size: 100 })
    if (response.code === 200) {
      advertiserList.value = response.data || []
    }
  } catch (error) {
    logger.error('加载广告主列表失败:', error)
  }
}

const loadPublishers = async () => {
  try {
    const response = await getPublishers({ page: 1, page_size: 100 })
    if (response.code === 200) {
      publisherList.value = response.data || []
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
      cap_type: filterCapType.value || undefined,
      offer_id: filterOffer.value || undefined,
      publisher_id: filterPublisher.value || undefined,
      is_active: filterActive.value !== null ? filterActive.value : undefined
    }
    const response = await getCaps(params)
    if (response.code === 200) {
      tableData.value = response.data || []
      pagination.total = response.total || 0
    } else {
      ElMessage.error(response.message || '获取数据失败')
    }
  } catch (error) {
    logger.error('获取Cap配置列表失败:', error)
    ElMessage.error('获取数据失败')
  } finally {
    loading.value = false
  }
}

// Cap类型改变
const handleCapTypeChange = () => {
  if (formData.cap_type !== 'advertiser_offer') {
    formData.advertiser_id = null
  }
}

// 搜索
const handleSearch = () => {
  pagination.page = 1
  loadData()
}

// 重置
const handleReset = () => {
  filterCapType.value = null
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
    cap_type: 'offer',
    advertiser_id: null,
    offer_id: null,
    publisher_id: null,
    daily_cap: null,
    total_cap: null,
    is_active: true
  })
  dialogVisible.value = true
}

// 编辑
const handleEdit = (row) => {
  isEdit.value = true
  Object.assign(formData, {
    id: row.id,
    cap_type: row.cap_type,
    advertiser_id: row.advertiser_id,
    offer_id: row.offer_id,
    publisher_id: row.publisher_id,
    daily_cap: row.daily_cap,
    total_cap: row.total_cap,
    is_active: row.is_active
  })
  dialogVisible.value = true
}

// 删除
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除此Cap配置吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const response = await deleteCap(row.id)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      loadData()
    } else {
      ElMessage.error(response.message || '删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      logger.error('删除Cap配置失败:', error)
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
        response = await updateCap(formData.id, formData)
      } else {
        response = await createCap(formData)
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
  loadAdvertisers()
  loadPublishers()
  loadData()
})
</script>

<style scoped>
.cap-management {
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
</style>

