<template>
  <div class="conversion-deduction-management">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Setting /></el-icon>
            <span class="header-title">转化扣减配置管理</span>
          </div>
          <el-button type="primary" :icon="Plus" @click="handleAdd">添加配置</el-button>
        </div>
      </template>

      <!-- 搜索筛选区 -->
      <div class="search-bar">
        <el-input
          v-model="searchForm.keyword"
          placeholder="搜索配置对象名称"
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
          v-model="searchForm.level"
          placeholder="选择层级"
          clearable
          style="width: 150px; margin-left: 10px;"
          @change="handleSearch"
        >
          <el-option label="全部" :value="null" />
          <el-option label="广告主" value="advertiser" />
          <el-option label="Offer" value="offer" />
          <el-option label="渠道" value="publisher" />
        </el-select>
        
        <el-select
          v-model="searchForm.is_active"
          placeholder="选择状态"
          clearable
          style="width: 150px; margin-left: 10px;"
          @change="handleSearch"
        >
          <el-option label="全部" :value="null" />
          <el-option label="启用" :value="true" />
          <el-option label="禁用" :value="false" />
        </el-select>
        
        <el-button type="primary" :icon="Search" @click="handleSearch" style="margin-left: 10px;">
          搜索
        </el-button>
        <el-button :icon="Refresh" @click="handleReset">重置</el-button>
      </div>

      <!-- 配置列表表格 -->
      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        style="width: 100%; margin-top: 20px;"
      >
        <el-table-column prop="id" label="ID" width="80" />
        
        <el-table-column prop="level" label="层级" width="100" align="center">
          <template #default="scope">
            <el-tag :type="getLevelTagType(scope.row.level)">
              {{ getLevelLabel(scope.row.level) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="target_name" label="配置对象" min-width="200" />
        
        <el-table-column label="扣量配置" width="180" align="center">
          <template #default="scope">
            <div v-if="scope.row.enable_volume_deduction" class="deduction-cell volume-deduction">
              <div class="deduction-header">
                <el-icon class="deduction-icon" style="color: #E6A23C;"><Remove /></el-icon>
                <span class="deduction-label">扣量</span>
              </div>
              <el-tag type="warning" size="small" style="margin-top: 4px;">
                {{ (scope.row.volume_deduction_ratio * 100).toFixed(1) }}%
              </el-tag>
              <div class="deduction-strategy">
                <el-tag size="small" type="info" effect="plain">
                  {{ getStrategyLabel(scope.row.deduction_strategy) }}
                </el-tag>
              </div>
            </div>
            <div v-else class="deduction-disabled">
              <el-icon><Close /></el-icon>
              <span>未启用扣量</span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column label="扣金额配置" width="150" align="center">
          <template #default="scope">
            <div v-if="scope.row.enable_amount_deduction" class="deduction-cell amount-deduction">
              <div class="deduction-header">
                <el-icon class="deduction-icon" style="color: #F56C6C;"><Money /></el-icon>
                <span class="deduction-label">扣金额</span>
              </div>
              <el-tag type="danger" size="small" style="margin-top: 4px;">
                {{ (scope.row.amount_deduction_ratio * 100).toFixed(1) }}%
              </el-tag>
              <div class="deduction-tip">每个转化扣减</div>
            </div>
            <div v-else class="deduction-disabled">
              <el-icon><Close /></el-icon>
              <span>未启用扣金额</span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="priority" label="优先级" width="100" align="center" />
        
        <el-table-column prop="is_active" label="状态" width="100" align="center">
          <template #default="scope">
            <el-switch
              v-model="scope.row.is_active"
              @change="handleStatusChange(scope.row)"
            />
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="180" align="center" fixed="right">
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
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 添加/编辑配置对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'add' ? '添加扣减配置' : '编辑扣减配置'"
      width="600px"
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="120px"
        label-position="right"
      >
        <!-- 配置层级 -->
        <el-form-item label="配置层级" prop="level">
          <el-radio-group v-model="form.level" @change="handleLevelChange">
            <el-radio label="advertiser">广告主</el-radio>
            <el-radio label="offer">Offer</el-radio>
            <el-radio label="publisher">渠道</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <!-- 配置对象选择 -->
        <el-form-item label="配置对象" prop="target_id">
          <el-select
            v-model="form.target_id"
            :placeholder="`请选择${getLevelLabel(form.level)}`"
            filterable
            style="width: 100%;"
            :loading="targetLoading"
          >
            <el-option
              v-for="item in targetOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        
        <!-- 按比例扣量配置 -->
        <el-divider content-position="left">
          <div class="divider-content">
            <el-icon style="color: #E6A23C; margin-right: 8px;"><Remove /></el-icon>
            <span style="font-weight: 600; color: #E6A23C;">按比例扣量</span>
            <span class="divider-desc">（减少转化数量，下游不可见）</span>
          </div>
        </el-divider>
        
        <el-form-item label="启用扣量">
          <el-switch 
            v-model="form.enable_volume_deduction" 
            active-text="启用"
            inactive-text="禁用"
          />
          <div class="form-item-tip" style="margin-top: 8px;">
            <el-icon><InfoFilled /></el-icon>
            扣量：减少转化数量，被扣减的转化不会保存到数据库，下游渠道无法看到
          </div>
        </el-form-item>
        
        <template v-if="form.enable_volume_deduction">
          <el-form-item label="扣量比例" prop="volume_deduction_ratio">
            <div style="display: flex; align-items: center; width: 100%;">
              <el-slider
                v-model="volumeRatioPercent"
                :min="0"
                :max="100"
                :step="0.1"
                show-input
                :show-input-controls="false"
                style="flex: 1; margin-right: 20px;"
              />
              <el-input-number
                v-model="volumeRatioPercent"
                :min="0"
                :max="100"
                :precision="2"
                :step="0.1"
                style="width: 120px;"
              />
              <span style="margin-left: 10px; font-weight: 600; color: #E6A23C;">%</span>
            </div>
            <div class="form-item-tip">
              <strong>扣量比例说明：</strong>范围 0% - 100%，例如：10% 表示扣减10%的转化数量。
              被扣减的转化不会保存到数据库，下游渠道无法看到这些转化。
            </div>
          </el-form-item>
          
          <el-form-item label="扣减策略" prop="deduction_strategy">
            <el-select v-model="form.deduction_strategy" style="width: 100%;">
              <el-option label="随机" value="random">
                <div>
                  <div><strong>随机</strong></div>
                  <div style="font-size: 12px; color: #909399;">随机选择转化进行扣减，分布更自然</div>
                </div>
              </el-option>
              <el-option label="按比例" value="proportional">
                <div>
                  <div><strong>按比例</strong></div>
                  <div style="font-size: 12px; color: #909399;">按时间顺序等比例选择转化进行扣减</div>
                </div>
              </el-option>
              <el-option label="轮询" value="round_robin">
                <div>
                  <div><strong>轮询</strong></div>
                  <div style="font-size: 12px; color: #909399;">轮询选择转化进行扣减</div>
                </div>
              </el-option>
            </el-select>
            <div class="form-item-tip">
              选择扣量时的分配策略，影响哪些转化会被扣减
            </div>
          </el-form-item>
        </template>
        
        <!-- 按比例扣金额配置 -->
        <el-divider content-position="left">
          <div class="divider-content">
            <el-icon style="color: #F56C6C; margin-right: 8px;"><Money /></el-icon>
            <span style="font-weight: 600; color: #F56C6C;">按比例扣金额</span>
            <span class="divider-desc">（减少转化金额，下游可见但金额减少）</span>
          </div>
        </el-divider>
        
        <el-form-item label="启用扣金额">
          <el-switch 
            v-model="form.enable_amount_deduction" 
            active-text="启用"
            inactive-text="禁用"
          />
          <div class="form-item-tip" style="margin-top: 8px;">
            <el-icon><InfoFilled /></el-icon>
            扣金额：减少转化金额，转化仍然保存但金额会按比例减少，下游可以看到转化但金额已扣减
          </div>
        </el-form-item>
        
        <template v-if="form.enable_amount_deduction">
          <el-form-item label="扣金额比例" prop="amount_deduction_ratio">
            <div style="display: flex; align-items: center; width: 100%;">
              <el-slider
                v-model="amountRatioPercent"
                :min="0"
                :max="100"
                :step="0.1"
                show-input
                :show-input-controls="false"
                style="flex: 1; margin-right: 20px;"
              />
              <el-input-number
                v-model="amountRatioPercent"
                :min="0"
                :max="100"
                :precision="2"
                :step="0.1"
                style="width: 120px;"
              />
              <span style="margin-left: 10px; font-weight: 600; color: #F56C6C;">%</span>
            </div>
            <div class="form-item-tip">
              <strong>扣金额比例说明：</strong>范围 0% - 100%，例如：5% 表示每个转化金额扣减5%。
              转化仍然保存到数据库，但最终支付给下游的金额会按比例减少。
            </div>
          </el-form-item>
        </template>
        
        <!-- 优先级 -->
        <el-form-item label="优先级" prop="priority">
          <el-input-number
            v-model="form.priority"
            :min="0"
            :max="100"
            style="width: 100%;"
          />
          <div class="form-item-tip">
            数字越大优先级越高，相同层级时优先级高的配置生效
          </div>
        </el-form-item>
        
        <!-- 状态 -->
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="handleDialogClose">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Plus, Setting, Remove, Money, Close, InfoFilled } from '@element-plus/icons-vue'
import {
  getDeductionConfigs,
  createDeductionConfig,
  updateDeductionConfig,
  deleteDeductionConfig,
  updateDeductionConfigStatus
} from '@/api/deduction'
import { getAdvertisers } from '@/api/advertiser'
import { getOffers } from '@/api/offer'
import { getPublishers } from '@/api/publisher'

const loading = ref(false)
const tableData = ref([])
const dialogVisible = ref(false)
const dialogMode = ref('add')
const currentConfig = ref(null)
const submitting = ref(false)
const targetLoading = ref(false)
const targetOptions = ref([])

const searchForm = reactive({
  keyword: '',
  level: null,
  is_active: null
})

const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

const form = reactive({
  level: 'advertiser',
  target_id: null,
  enable_volume_deduction: false,
  volume_deduction_ratio: 0,
  deduction_strategy: 'random',
  enable_amount_deduction: false,
  amount_deduction_ratio: 0,
  priority: 0,
  is_active: true
})

// 百分比显示（用于滑块和输入框）
const volumeRatioPercent = computed({
  get: () => form.volume_deduction_ratio * 100,
  set: (val) => {
    form.volume_deduction_ratio = val / 100
  }
})

const amountRatioPercent = computed({
  get: () => form.amount_deduction_ratio * 100,
  set: (val) => {
    form.amount_deduction_ratio = val / 100
  }
})

const formRef = ref(null)

// 表单验证规则
const rules = {
  level: [
    { required: true, message: '请选择配置层级', trigger: 'change' }
  ],
  target_id: [
    { required: true, message: '请选择配置对象', trigger: 'change' }
  ]
}

// 获取配置列表
const fetchData = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.page_size,
      ...searchForm
    }
    const response = await getDeductionConfigs(params)
    if (response.code === 200) {
      // 处理分页响应格式
      const data = response.data || {}
      tableData.value = data.data || data.items || []
      pagination.total = data.total || response.total || 0
    }
  } catch (error) {
    ElMessage.error('获取配置列表失败：' + (error.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// 搜索
const handleSearch = () => {
  pagination.page = 1
  fetchData()
}

// 重置
const handleReset = () => {
  searchForm.keyword = ''
  searchForm.level = null
  searchForm.is_active = null
  handleSearch()
}

// 添加配置
const handleAdd = () => {
  dialogMode.value = 'add'
  currentConfig.value = null
  resetForm()
  dialogVisible.value = true
}

// 编辑配置
const handleEdit = (row) => {
  dialogMode.value = 'edit'
  currentConfig.value = { ...row }
  Object.assign(form, {
    level: row.level,
    target_id: row.target_id,
    enable_volume_deduction: row.enable_volume_deduction,
    volume_deduction_ratio: row.volume_deduction_ratio,
    deduction_strategy: row.deduction_strategy,
    enable_amount_deduction: row.enable_amount_deduction,
    amount_deduction_ratio: row.amount_deduction_ratio,
    priority: row.priority,
    is_active: row.is_active
  })
  handleLevelChange(row.level)
  dialogVisible.value = true
}

// 删除配置
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除配置"${row.target_name}"吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    await deleteDeductionConfig(row.id)
    ElMessage.success('删除成功')
    fetchData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败：' + (error.message || '未知错误'))
    }
  }
}

// 状态变更
const handleStatusChange = async (row) => {
  try {
    await updateDeductionConfigStatus(row.id, row.is_active)
    ElMessage.success('状态更新成功')
  } catch (error) {
    row.is_active = !row.is_active // 回滚
    ElMessage.error('状态更新失败：' + (error.message || '未知错误'))
  }
}

// 层级变化
const handleLevelChange = async (level) => {
  form.target_id = null
  targetOptions.value = []
  
  if (!level) return
  
  targetLoading.value = true
  try {
    let response
    if (level === 'advertiser') {
      response = await getAdvertisers({ page_size: 1000 })
    } else if (level === 'offer') {
      response = await getOffers({ page_size: 1000 })
    } else if (level === 'publisher') {
      response = await getPublishers({ page_size: 1000 })
    }
    
    if (response && response.code === 200) {
      const data = response.data || {}
      const items = data.data || data.items || (Array.isArray(data) ? data : [])
      targetOptions.value = items.map(item => ({
        id: item.id,
        name: item.advertiser_name || item.offer_name || item.publisher_name
      }))
    }
  } catch (error) {
    ElMessage.error('加载配置对象列表失败：' + (error.message || '未知错误'))
  } finally {
    targetLoading.value = false
  }
}

// 提交表单
const handleSubmit = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    // 验证至少启用一种扣减方式
    if (!form.enable_volume_deduction && !form.enable_amount_deduction) {
      ElMessage.warning('请至少启用一种扣减方式（扣量或扣金额）')
      return
    }
    
    submitting.value = true
    try {
      const data = {
        level: form.level,
        target_id: form.target_id,
        enable_volume_deduction: form.enable_volume_deduction,
        volume_deduction_ratio: form.enable_volume_deduction ? form.volume_deduction_ratio : 0,
        deduction_strategy: form.enable_volume_deduction ? form.deduction_strategy : 'random',
        enable_amount_deduction: form.enable_amount_deduction,
        amount_deduction_ratio: form.enable_amount_deduction ? form.amount_deduction_ratio : 0,
        priority: form.priority,
        is_active: form.is_active
      }
      
      if (dialogMode.value === 'add') {
        await createDeductionConfig(data)
        ElMessage.success('添加成功')
      } else {
        await updateDeductionConfig(currentConfig.value.id, data)
        ElMessage.success('更新成功')
      }
      
      dialogVisible.value = false
      fetchData()
    } catch (error) {
      ElMessage.error((dialogMode.value === 'add' ? '添加' : '更新') + '失败：' + (error.message || '未知错误'))
    } finally {
      submitting.value = false
    }
  })
}

// 关闭对话框
const handleDialogClose = () => {
  dialogVisible.value = false
  resetForm()
}

// 重置表单
const resetForm = () => {
  Object.assign(form, {
    level: 'advertiser',
    target_id: null,
    enable_volume_deduction: false,
    volume_deduction_ratio: 0,
    deduction_strategy: 'random',
    enable_amount_deduction: false,
    amount_deduction_ratio: 0,
    priority: 0,
    is_active: true
  })
  targetOptions.value = []
  if (formRef.value) {
    formRef.value.clearValidate()
  }
}

// 分页
const handlePageChange = (page) => {
  pagination.page = page
  fetchData()
}

const handleSizeChange = (size) => {
  pagination.page_size = size
  pagination.page = 1
  fetchData()
}

// 工具方法
const getLevelLabel = (level) => {
  const map = {
    'advertiser': '广告主',
    'offer': 'Offer',
    'publisher': '渠道'
  }
  return map[level] || level
}

const getLevelTagType = (level) => {
  const map = {
    'advertiser': 'primary',
    'offer': 'success',
    'publisher': 'warning'
  }
  return map[level] || ''
}

const getStrategyLabel = (strategy) => {
  const map = {
    'random': '随机',
    'proportional': '按比例',
    'round_robin': '轮询'
  }
  return map[strategy] || strategy
}

// 监听对话框显示，初始化表单
watch(dialogVisible, (val) => {
  if (val) {
    if (dialogMode.value === 'edit' && currentConfig.value) {
      // 编辑模式已在handleEdit中处理
    } else {
      handleLevelChange('advertiser')
    }
  }
})

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.conversion-deduction-management {
  padding: 20px;
}

.page-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
}

.header-icon {
  font-size: 20px;
  margin-right: 8px;
  color: #409EFF;
}

.header-title {
  font-size: 18px;
  font-weight: 500;
}

.search-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.table-wrapper {
  margin-top: 20px;
}

.pagination-wrapper {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.form-item-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.6;
  display: flex;
  align-items: flex-start;
  gap: 4px;
}

.form-item-tip .el-icon {
  margin-top: 2px;
  flex-shrink: 0;
}

.divider-content {
  display: flex;
  align-items: center;
}

.divider-desc {
  font-size: 12px;
  font-weight: normal;
  color: #909399;
  margin-left: 8px;
}

.deduction-cell {
  padding: 8px;
  border-radius: 4px;
  text-align: center;
}

.deduction-cell.volume-deduction {
  background-color: #FDF6EC;
  border: 1px solid #F5DAB1;
}

.deduction-cell.amount-deduction {
  background-color: #FEF0F0;
  border: 1px solid #FBC4C4;
}

.deduction-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin-bottom: 4px;
}

.deduction-icon {
  font-size: 16px;
}

.deduction-label {
  font-weight: 600;
  font-size: 13px;
}

.deduction-strategy {
  margin-top: 6px;
}

.deduction-tip {
  font-size: 11px;
  color: #909399;
  margin-top: 4px;
}

.deduction-disabled {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: #C0C4CC;
  font-size: 12px;
  padding: 8px;
}
</style>


