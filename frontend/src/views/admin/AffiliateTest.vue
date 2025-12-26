<template>
  <div class="affiliate-test">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Download /></el-icon>
            <span class="header-title">下游测试</span>
          </div>
          <el-button type="primary" :icon="Plus" @click="handleAdd">创建测试</el-button>
        </div>
      </template>

      <!-- 搜索栏 -->
      <div class="search-bar">
        <el-select
          v-model="filterPublisher"
          placeholder="渠道"
          clearable
          filterable
          style="width: 200px;"
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
          v-model="filterStatus"
          placeholder="状态"
          clearable
          style="width: 150px; margin-left: 10px;"
          @change="handleSearch"
        >
          <el-option label="全部" :value="null" />
          <el-option label="Send Success" value="Send Success" />
          <el-option label="Failed" value="Failed" />
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
        <el-table-column prop="publisher_name" label="渠道" width="150" />
        <el-table-column prop="offer_name" label="Offer" min-width="200" />
        <el-table-column prop="click_id" label="Click ID" min-width="200">
          <template #default="scope">
            <el-button type="primary" link @click="copyToClipboard(scope.row.click_id)">
              {{ scope.row.click_id }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column prop="price" label="价格" width="100" align="right">
          <template #default="scope">
            <span v-if="scope.row.price">{{ scope.row.price.toFixed(2) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="country" label="国家" width="100" />
        <el-table-column prop="status" label="状态" width="120" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'Send Success' ? 'success' : 'danger'">
              {{ scope.row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="postback_time" label="发送时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.postback_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="scope">
            <el-button type="primary" link :icon="View" @click="handleView(scope.row)">查看</el-button>
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

    <!-- 创建测试对话框 -->
    <el-dialog
      v-model="dialogVisible"
      title="创建下游测试"
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

        <el-form-item label="Click ID" prop="click_id">
          <el-input
            v-model="formData.click_id"
            placeholder="请输入下游提供的Click ID"
          />
          <div class="form-hint">下游提供的Click ID，用于测试Postback发送</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">发送测试</el-button>
      </template>
    </el-dialog>

    <!-- 查看详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="测试详情"
      width="800px"
    >
      <el-descriptions :column="2" border>
        <el-descriptions-item label="渠道">{{ currentTest?.publisher_name }}</el-descriptions-item>
        <el-descriptions-item label="Offer">{{ currentTest?.offer_name }}</el-descriptions-item>
        <el-descriptions-item label="Click ID" :span="2">
          <el-input :value="currentTest?.click_id" readonly>
            <template #append>
              <el-button @click="copyToClipboard(currentTest?.click_id)">复制</el-button>
            </template>
          </el-input>
        </el-descriptions-item>
        <el-descriptions-item label="价格">{{ currentTest?.price ? currentTest.price.toFixed(2) : '-' }}</el-descriptions-item>
        <el-descriptions-item label="国家">{{ currentTest?.country || '-' }}</el-descriptions-item>
        <el-descriptions-item label="平台">{{ currentTest?.platform || '-' }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="currentTest?.status === 'Send Success' ? 'success' : 'danger'">
            {{ currentTest?.status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="发送时间">{{ currentTest?.postback_time ? formatDate(currentTest.postback_time) : '-' }}</el-descriptions-item>
        <el-descriptions-item label="返回内容" :span="2">
          <el-input
            :value="currentTest?.affiliate_return_content || '-'"
            readonly
            type="textarea"
            :rows="5"
          />
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Search, Refresh, View, Download } from '@element-plus/icons-vue'
import { getAffiliateTests, createAffiliateTest } from '@/api/affiliateTest'
import { getPublishers } from '@/api/publisher'
import { getOffers } from '@/api/offer'
import { logger } from '@/utils/logger'
import { formatDate } from '@/utils/date'

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const detailDialogVisible = ref(false)
const filterPublisher = ref(null)
const filterOffer = ref(null)
const filterStatus = ref(null)
const formRef = ref(null)

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const tableData = ref([])
const publisherList = ref([])
const offerList = ref([])
const currentTest = ref(null)

const formData = reactive({
  publisher_id: null,
  offer_id: null,
  click_id: ''
})

const formRules = {
  publisher_id: [
    { required: true, message: '请选择渠道', trigger: 'change' }
  ],
  offer_id: [
    { required: true, message: '请选择Offer', trigger: 'change' }
  ],
  click_id: [
    { required: true, message: '请输入Click ID', trigger: 'blur' }
  ]
}

// 加载基础数据
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

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: Math.min(pagination.pageSize, 100),
      publisher_id: filterPublisher.value || undefined,
      offer_id: filterOffer.value || undefined,
      status: filterStatus.value || undefined
    }
    const response = await getAffiliateTests(params)
    if (response.code === 200) {
      tableData.value = response.data || []
      pagination.total = response.total || 0
    } else {
      ElMessage.error(response.message || '获取数据失败')
    }
  } catch (error) {
    logger.error('获取测试记录列表失败:', error)
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
  filterPublisher.value = null
  filterOffer.value = null
  filterStatus.value = null
  pagination.page = 1
  loadData()
}

// 添加
const handleAdd = () => {
  Object.assign(formData, {
    publisher_id: null,
    offer_id: null,
    click_id: ''
  })
  dialogVisible.value = true
}

// 查看
const handleView = (row) => {
  currentTest.value = row
  detailDialogVisible.value = true
}

// 复制到剪贴板
const copyToClipboard = async (text) => {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    logger.error('复制失败:', error)
    ElMessage.error('复制失败')
  }
}

// 提交
const handleSubmit = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    submitting.value = true
    try {
      const response = await createAffiliateTest(formData)
      if (response.code === 200) {
        ElMessage.success('测试记录创建成功，Postback已发送')
        dialogVisible.value = false
        loadData()
      } else {
        ElMessage.error(response.message || '创建失败')
      }
    } catch (error) {
      logger.error('创建测试记录失败:', error)
      ElMessage.error('创建失败')
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
  loadPublishers()
  loadOffers()
  loadData()
})
</script>

<style scoped>
.affiliate-test {
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

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}
</style>

