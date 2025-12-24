<template>
  <div class="offer-management">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Box /></el-icon>
            <span class="header-title">Offer管理</span>
          </div>
          <el-button type="primary" :icon="Plus" @click="handleAdd">添加Offer</el-button>
        </div>
      </template>

      <!-- 搜索栏 -->
      <div class="search-bar">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索Offer名称或ID"
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
          v-model="filterAdvertiser"
          placeholder="请选择广告主"
          clearable
          filterable
          style="width: 180px; margin-left: 10px; min-width: 180px;"
          @change="handleSearch"
        >
          <el-option
            v-for="adv in advertiserList"
            :key="adv.id"
            :label="adv.advertiser_name"
            :value="adv.id"
          />
        </el-select>
        <el-select
          v-model="filterStatus"
          placeholder="请选择状态"
          clearable
          style="width: 140px; margin-left: 10px; min-width: 140px;"
          @change="handleSearch"
        >
          <el-option label="全部" :value="null" />
          <el-option label="Active" value="Active" />
          <el-option label="Inactive" value="Inactive" />
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
      <div class="table-wrapper">
        <el-table
          v-loading="loading"
          :data="tableData"
          stripe
          style="width: 100%; margin-top: 20px;"
        >
        <el-table-column prop="id" label="Offer ID" width="100" align="center" />
        <el-table-column prop="offer_name" label="Offer名称" width="180" show-overflow-tooltip />
        <el-table-column prop="advertiser_name" label="广告主" width="150" />
        <el-table-column prop="advertiser_offer_id" label="上游Offer ID" width="150" />
        <el-table-column prop="payout" label="上游PO" width="100" align="right">
          <template #default="scope">
            <span v-if="scope.row.payout">{{ scope.row.payout.toFixed(2) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="affiliate_payout" label="下游PO" width="100" align="right">
          <template #default="scope">
            <span v-if="scope.row.affiliate_payout">{{ scope.row.affiliate_payout.toFixed(2) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="country" label="国家" width="100" />
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'Active' ? 'success' : 'info'">
              {{ scope.row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="激活" width="80" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.is_active ? 'success' : 'danger'">
              {{ scope.row.is_active ? '是' : '否' }}
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
      </div>

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
      :title="isEdit ? '编辑Offer' : '添加Offer'"
      width="900px"
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="120px"
      >
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="Offer名称" prop="offer_name">
              <el-input v-model="formData.offer_name" placeholder="请输入Offer名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="广告主" prop="advertiser_id">
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
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="上游Offer ID" prop="advertiser_offer_id">
              <el-input v-model="formData.advertiser_offer_id" placeholder="上游系统中的Offer ID（可选）" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="国家" prop="country">
              <el-input v-model="formData.country" placeholder="国家（可选）" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="分类" prop="category">
              <el-input v-model="formData.category" placeholder="分类（可选）" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="类型" prop="type">
              <el-input v-model="formData.type" placeholder="类型（可选）" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="上游PO" prop="payout">
              <el-input-number
                v-model="formData.payout"
                :min="0"
                :precision="2"
                placeholder="上游支付金额"
                style="width: 100%;"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="下游PO" prop="affiliate_payout">
              <el-input-number
                v-model="formData.affiliate_payout"
                :min="0"
                :precision="2"
                placeholder="扣价后给渠道的金额"
                style="width: 100%;"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="上游Cap" prop="upstream_cap">
              <el-input-number
                v-model="formData.upstream_cap"
                :min="0"
                placeholder="上游转化上限"
                style="width: 100%;"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="下游Cap" prop="downstream_cap">
              <el-input-number
                v-model="formData.downstream_cap"
                :min="0"
                placeholder="下游转化上限"
                style="width: 100%;"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="预览链接" prop="preview_link">
          <el-input v-model="formData.preview_link" placeholder="预览链接（可选）" />
        </el-form-item>

        <el-form-item label="上游Tracklink" prop="advertiser_tracklink">
          <el-input
            v-model="formData.advertiser_tracklink"
            type="textarea"
            :rows="2"
            placeholder="上游的Tracklink（不显示给下游，建立单子时配置我们的参数）"
          />
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="Postback URL" prop="postback_url">
              <el-input v-model="formData.postback_url" placeholder="Postback URL（可选）" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Postback方法" prop="postback_method">
              <el-select v-model="formData.postback_method" style="width: 100%;">
                <el-option label="GET" value="GET" />
                <el-option label="POST" value="POST" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="分配渠道" prop="publisher_ids">
          <el-select
            v-model="formData.publisher_ids"
            multiple
            placeholder="请选择分配的渠道"
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

        <el-form-item label="点击有效期(小时)" prop="click_validity_hours">
          <el-input-number
            v-model="formData.click_validity_hours"
            :min="1"
            :max="8760"
            placeholder="默认720小时(30天)"
            style="width: 100%;"
          />
          <div class="form-hint">点击有效期，超过此时间的点击将无法关联转化。默认720小时（30天）</div>
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="状态" prop="status">
              <el-select v-model="formData.status" style="width: 100%;">
                <el-option label="Active" value="Active" />
                <el-option label="Inactive" value="Inactive" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="激活" prop="is_active">
              <el-switch v-model="formData.is_active" />
            </el-form-item>
          </el-col>
        </el-row>
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
import { Plus, Search, Refresh, Edit, Delete, Box } from '@element-plus/icons-vue'
import { getOffers, createOffer, updateOffer, deleteOffer } from '@/api/offer'
import { getAdvertisers } from '@/api/advertiser'
import { getPublishers } from '@/api/publisher'
import { logger } from '@/utils/logger'
import { formatDate } from '@/utils/date'

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const searchKeyword = ref('')
const filterAdvertiser = ref(null)
const filterStatus = ref(null)
const filterActive = ref(null)
const formRef = ref(null)

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const tableData = ref([])
const advertiserList = ref([])
const publisherList = ref([])

const formData = reactive({
  offer_name: '',
  advertiser_id: null,
  advertiser_offer_id: '',
  preview_link: '',
  payout: null,
  affiliate_payout: null,
  country: '',
  category: '',
  type: '',
  status: 'Active',
  upstream_cap: null,
  downstream_cap: null,
  advertiser_tracklink: '',
  postback_url: '',
  postback_method: 'GET',
  click_validity_hours: 720,
  publisher_ids: [],
  is_active: true
})

const formRules = {
  offer_name: [
    { required: true, message: '请输入Offer名称', trigger: 'blur' }
  ],
  advertiser_id: [
    { required: true, message: '请选择广告主', trigger: 'change' }
  ]
}

// 加载广告主列表
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

// 加载渠道列表
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
      search: searchKeyword.value || undefined,
      advertiser_id: filterAdvertiser.value || undefined,
      status: filterStatus.value || undefined,
      is_active: filterActive.value !== null ? filterActive.value : undefined
    }
    const response = await getOffers(params)
    if (response.code === 200) {
      tableData.value = response.data || []
      pagination.total = response.total || 0
    } else {
      ElMessage.error(response.message || '获取数据失败')
    }
  } catch (error) {
    logger.error('获取Offer列表失败:', error)
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
  filterAdvertiser.value = null
  filterStatus.value = null
  filterActive.value = null
  pagination.page = 1
  loadData()
}

// 添加
const handleAdd = () => {
  isEdit.value = false
  Object.assign(formData, {
    offer_name: '',
    advertiser_id: null,
    advertiser_offer_id: '',
    preview_link: '',
    payout: null,
    affiliate_payout: null,
    country: '',
    category: '',
    type: '',
    status: 'Active',
    upstream_cap: null,
    downstream_cap: null,
    advertiser_tracklink: '',
    postback_url: '',
    postback_method: 'GET',
    click_validity_hours: 720,
    publisher_ids: [],
    is_active: true
  })
  dialogVisible.value = true
}

// 编辑
const handleEdit = (row) => {
  isEdit.value = true
  Object.assign(formData, {
    id: row.id,
    offer_name: row.offer_name,
    advertiser_id: row.advertiser_id,
    advertiser_offer_id: row.advertiser_offer_id || '',
    preview_link: row.preview_link || '',
    payout: row.payout,
    affiliate_payout: row.affiliate_payout,
    country: row.country || '',
    category: row.category || '',
    type: row.type || '',
    status: row.status,
    upstream_cap: row.upstream_cap,
    downstream_cap: row.downstream_cap,
    advertiser_tracklink: row.advertiser_tracklink || '',
    postback_url: row.postback_url || '',
    postback_method: row.postback_method || 'GET',
    click_validity_hours: row.click_validity_hours || 720,
    publisher_ids: row.assigned_publishers ? row.assigned_publishers.map(p => p.id) : [],
    is_active: row.is_active
  })
  dialogVisible.value = true
}

// 删除
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除Offer "${row.offer_name}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const response = await deleteOffer(row.id)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      loadData()
    } else {
      ElMessage.error(response.message || '删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      logger.error('删除Offer失败:', error)
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
        response = await updateOffer(formData.id, formData)
      } else {
        response = await createOffer(formData)
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
  loadAdvertisers()
  loadPublishers()
  loadData()
})
</script>

<style scoped>
.offer-management {
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
  min-width: 1200px;
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
  .offer-management {
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
    min-width: 1100px;
    font-size: 12px;
  }

  .table-wrapper :deep(.el-table__cell) {
    padding: 8px 4px;
  }
}
</style>

