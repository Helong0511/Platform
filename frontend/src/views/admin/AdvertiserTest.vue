<template>
  <div class="advertiser-test">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Upload /></el-icon>
            <span class="header-title">上游测试</span>
          </div>
          <el-button type="primary" :icon="Plus" @click="handleAdd">创建测试</el-button>
        </div>
      </template>

      <!-- 搜索栏 -->
      <div class="search-bar">
        <el-select
          v-model="filterAdvertiser"
          placeholder="广告主"
          clearable
          filterable
          style="width: 200px;"
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
        <el-table-column prop="advertiser_name" label="广告主" width="150" />
        <el-table-column prop="offer_name" label="Offer" min-width="200" />
        <el-table-column prop="advertiser_offer_id" label="上游Offer ID" width="150" />
        <el-table-column prop="price" label="价格" width="100" align="right">
          <template #default="scope">
            <span v-if="scope.row.price">{{ scope.row.price.toFixed(2) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="country" label="国家" width="100" />
        <el-table-column prop="click_id" label="Click ID" min-width="200">
          <template #default="scope">
            <el-button type="primary" link @click="copyToClipboard(scope.row.click_id)">
              {{ scope.row.click_id }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column prop="click_url" label="Click Url" min-width="300">
          <template #default="scope">
            <el-button type="primary" link @click="copyToClipboard(scope.row.click_url)">
              {{ scope.row.click_url ? (scope.row.click_url.length > 50 ? scope.row.click_url.substring(0, 50) + '...' : scope.row.click_url) : '-' }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column prop="test_time" label="测试时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.test_time) }}
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
      title="创建上游测试"
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
        <el-form-item label="广告主" prop="advertiser_id">
          <el-select
            v-model="formData.advertiser_id"
            placeholder="请选择广告主"
            filterable
            style="width: 100%;"
            @change="handleAdvertiserChange"
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
              v-for="offer in filteredOffers"
              :key="offer.id"
              :label="offer.offer_name"
              :value="offer.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">创建测试</el-button>
      </template>
    </el-dialog>

    <!-- 查看详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="测试详情"
      width="800px"
      :append-to-body="true"
    >
      <el-descriptions :column="2" border>
        <el-descriptions-item label="广告主">{{ currentTest?.advertiser_name }}</el-descriptions-item>
        <el-descriptions-item label="Offer">{{ currentTest?.offer_name }}</el-descriptions-item>
        <el-descriptions-item label="上游Offer ID">{{ currentTest?.advertiser_offer_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="价格">{{ currentTest?.price ? currentTest.price.toFixed(2) : '-' }}</el-descriptions-item>
        <el-descriptions-item label="国家">{{ currentTest?.country || '-' }}</el-descriptions-item>
        <el-descriptions-item label="测试时间">{{ currentTest?.test_time ? formatDate(currentTest.test_time) : '-' }}</el-descriptions-item>
        <el-descriptions-item label="Click ID" :span="2">
          <el-input :value="currentTest?.click_id" readonly>
            <template #append>
              <el-button @click="copyToClipboard(currentTest?.click_id)">复制</el-button>
            </template>
          </el-input>
        </el-descriptions-item>
        <el-descriptions-item label="Click Url" :span="2">
          <el-input :value="currentTest?.click_url" readonly type="textarea" :rows="3">
            <template #append>
              <el-button @click="copyToClipboard(currentTest?.click_url)">复制</el-button>
            </template>
          </el-input>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Search, Refresh, View, Upload } from '@element-plus/icons-vue'
import { getAdvertiserTests, createAdvertiserTest } from '@/api/advertiserTest'
import { getAdvertisers } from '@/api/advertiser'
import { getOffers } from '@/api/offer'
import { logger } from '@/utils/logger'
import { formatDate } from '@/utils/date'

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const detailDialogVisible = ref(false)
const filterAdvertiser = ref(null)
const filterOffer = ref(null)
const formRef = ref(null)

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const tableData = ref([])
const advertiserList = ref([])
const offerList = ref([])
const currentTest = ref(null)

const formData = reactive({
  advertiser_id: null,
  offer_id: null
})

const formRules = {
  advertiser_id: [
    { required: true, message: '请选择广告主', trigger: 'change' }
  ],
  offer_id: [
    { required: true, message: '请选择Offer', trigger: 'change' }
  ]
}

// 根据广告主过滤Offer
const filteredOffers = computed(() => {
  if (!formData.advertiser_id) {
    return offerList.value
  }
  return offerList.value.filter(offer => offer.advertiser_id === formData.advertiser_id)
})

// 加载基础数据
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
      advertiser_id: filterAdvertiser.value || undefined,
      offer_id: filterOffer.value || undefined
    }
    const response = await getAdvertiserTests(params)
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

// 广告主改变
const handleAdvertiserChange = () => {
  formData.offer_id = null
}

// 搜索
const handleSearch = () => {
  pagination.page = 1
  loadData()
}

// 重置
const handleReset = () => {
  filterAdvertiser.value = null
  filterOffer.value = null
  pagination.page = 1
  loadData()
}

// 添加
const handleAdd = () => {
  Object.assign(formData, {
    advertiser_id: null,
    offer_id: null
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
      const response = await createAdvertiserTest(formData)
      if (response.code === 200) {
        ElMessage.success('测试记录创建成功')
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
  loadAdvertisers()
  loadOffers()
  loadData()
})
</script>

<style scoped>
.advertiser-test {
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
</style>

