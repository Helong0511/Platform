# CPL扣减系统前端界面详细设计

## 一、页面结构

### 1.1 路由配置

**路径**：`/app/admin/conversion-deductions`

**路由名称**：`ConversionDeductionManagement`

**权限要求**：需要管理员权限（`requiresAdmin: true`）

### 1.2 页面布局

```
┌─────────────────────────────────────────────────────────────────┐
│  转化扣减配置管理                                    [刷新] [导出]│
├─────────────────────────────────────────────────────────────────┤
│  ┌─ 搜索筛选区 ────────────────────────────────────────────┐   │
│  │ [搜索框: 搜索配置对象名称] [层级: 全部▼] [状态: 全部▼] │   │
│  │ [搜索] [重置]                                    [添加配置]│   │
│  └───────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  ┌─ 配置列表 ─────────────────────────────────────────────┐   │
│  │ ID │层级│配置对象│扣量│扣金额│策略│优先级│状态│操作      │   │
│  │────┼───┼──────┼───┼─────┼───┼─────┼───┼────────│   │
│  │ 1  │广告主│广告主A│10%│5%  │随机│0   │启用│[编辑][删除]│   │
│  │ 2  │Offer│OfferA │0% │10% │按比例│0│启用│[编辑][删除]│   │
│  │ 3  │渠道│渠道1  │15%│0%  │轮询│1   │禁用│[编辑][删除]│   │
│  └───────────────────────────────────────────────────────────┘   │
│  [分页控件]                                                       │
├─────────────────────────────────────────────────────────────────┤
│  ┌─ 扣减统计报表（标签页） ──────────────────────────────────┐   │
│  │ [按时间] [按广告主] [按Offer] [按渠道]                    │   │
│  │                                                             │   │
│  │ 时间范围：[2024-01-01] 至 [2024-01-31] [查询] [导出Excel] │   │
│  │                                                             │   │
│  │ ┌─ 总体统计 ───────────────────────────────────────┐     │   │
│  │ │ 原始转化数：1,000   扣减转化数：100   扣减率：10% │     │   │
│  │ │ 原始金额：$10,000   扣减金额：$1,000   扣减率：10%│     │   │
│  │ └──────────────────────────────────────────────────┘     │   │
│  │                                                             │   │
│  │ ┌─ 详细统计表格 ─────────────────────────────────────┐   │   │
│  │ │ 对象名称│原始转化│扣减转化│扣减率│原始金额│扣减金额│扣减率││   │
│  │ │────────┼──────┼──────┼─────┼──────┼──────┼─────││   │
│  │ │ 广告主A│600   │60    │10%  │$6,000│$600  │10% ││   │
│  │ │ 广告主B│400   │40    │10%  │$4,000│$400  │10% ││   │
│  │ └──────────────────────────────────────────────────┘   │   │
│  └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、组件设计

### 2.1 主页面组件（ConversionDeductionManagement.vue）

#### 2.1.1 组件结构

```vue
<template>
  <div class="conversion-deduction-management">
    <!-- 页面标题 -->
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Setting /></el-icon>
            <span class="header-title">转化扣减配置管理</span>
          </div>
          <div class="header-right">
            <el-button :icon="Refresh" @click="handleRefresh">刷新</el-button>
            <el-button type="primary" :icon="Plus" @click="handleAdd">添加配置</el-button>
          </div>
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
      <div class="table-wrapper">
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
          
          <el-table-column label="扣量配置" width="150" align="center">
            <template #default="scope">
              <div v-if="scope.row.enable_volume_deduction">
                <el-tag type="warning">{{ (scope.row.volume_deduction_ratio * 100).toFixed(1) }}%</el-tag>
                <div style="font-size: 12px; color: #909399; margin-top: 4px;">
                  {{ getStrategyLabel(scope.row.deduction_strategy) }}
                </div>
              </div>
              <span v-else style="color: #909399;">未启用</span>
            </template>
          </el-table-column>
          
          <el-table-column label="扣金额配置" width="120" align="center">
            <template #default="scope">
              <el-tag v-if="scope.row.enable_amount_deduction" type="danger">
                {{ (scope.row.amount_deduction_ratio * 100).toFixed(1) }}%
              </el-tag>
              <span v-else style="color: #909399;">未启用</span>
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
      </div>
    </el-card>

    <!-- 扣减统计报表 -->
    <el-card class="page-card" style="margin-top: 20px;">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><DataAnalysis /></el-icon>
            <span class="header-title">扣减统计报表</span>
          </div>
        </div>
      </template>

      <el-tabs v-model="statsTab" @tab-change="handleStatsTabChange">
        <el-tab-pane label="按时间" name="time">
          <StatsByTime ref="statsByTimeRef" />
        </el-tab-pane>
        <el-tab-pane label="按广告主" name="advertiser">
          <StatsByAdvertiser ref="statsByAdvertiserRef" />
        </el-tab-pane>
        <el-tab-pane label="按Offer" name="offer">
          <StatsByOffer ref="statsByOfferRef" />
        </el-tab-pane>
        <el-tab-pane label="按渠道" name="publisher">
          <StatsByPublisher ref="statsByPublisherRef" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 添加/编辑配置对话框 -->
    <DeductionConfigDialog
      v-model="dialogVisible"
      :config="currentConfig"
      :mode="dialogMode"
      @success="handleDialogSuccess"
    />
  </div>
</template>
```

#### 2.1.2 数据和方法

```javascript
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Plus, Setting, DataAnalysis } from '@element-plus/icons-vue'
import { getDeductionConfigs, deleteDeductionConfig, updateDeductionConfigStatus } from '@/api/deduction'
import DeductionConfigDialog from './components/DeductionConfigDialog.vue'
import StatsByTime from './components/StatsByTime.vue'
import StatsByAdvertiser from './components/StatsByAdvertiser.vue'
import StatsByOffer from './components/StatsByOffer.vue'
import StatsByPublisher from './components/StatsByPublisher.vue'

export default {
  name: 'ConversionDeductionManagement',
  components: {
    DeductionConfigDialog,
    StatsByTime,
    StatsByAdvertiser,
    StatsByOffer,
    StatsByPublisher
  },
  setup() {
    const loading = ref(false)
    const tableData = ref([])
    const dialogVisible = ref(false)
    const dialogMode = ref('add') // 'add' | 'edit'
    const currentConfig = ref(null)
    const statsTab = ref('time')
    
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
        tableData.value = response.data.items
        pagination.total = response.data.total
      } catch (error) {
        ElMessage.error('获取配置列表失败：' + error.message)
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
      dialogVisible.value = true
    }
    
    // 编辑配置
    const handleEdit = (row) => {
      dialogMode.value = 'edit'
      currentConfig.value = { ...row }
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
          ElMessage.error('删除失败：' + error.message)
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
        ElMessage.error('状态更新失败：' + error.message)
      }
    }
    
    // 对话框成功回调
    const handleDialogSuccess = () => {
      fetchData()
    }
    
    // 刷新
    const handleRefresh = () => {
      fetchData()
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
    
    // 统计标签页切换
    const handleStatsTabChange = (tabName) => {
      // 触发对应组件的刷新
      const refMap = {
        'time': 'statsByTimeRef',
        'advertiser': 'statsByAdvertiserRef',
        'offer': 'statsByOfferRef',
        'publisher': 'statsByPublisherRef'
      }
      // 这里可以通过ref调用子组件的方法
    }
    
    onMounted(() => {
      fetchData()
    })
    
    return {
      loading,
      tableData,
      searchForm,
      pagination,
      dialogVisible,
      dialogMode,
      currentConfig,
      statsTab,
      handleSearch,
      handleReset,
      handleAdd,
      handleEdit,
      handleDelete,
      handleStatusChange,
      handleDialogSuccess,
      handleRefresh,
      handlePageChange,
      handleSizeChange,
      getLevelLabel,
      getLevelTagType,
      getStrategyLabel,
      handleStatsTabChange
    }
  }
}
</script>
```

---

### 2.2 配置对话框组件（DeductionConfigDialog.vue）

#### 2.2.1 组件结构

```vue
<template>
  <el-dialog
    v-model="visible"
    :title="mode === 'add' ? '添加扣减配置' : '编辑扣减配置'"
    width="600px"
    @close="handleClose"
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
      <el-divider content-position="left">按比例扣量</el-divider>
      
      <el-form-item label="启用扣量">
        <el-switch v-model="form.enable_volume_deduction" />
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
              @change="handleVolumeRatioChange"
            />
            <span style="margin-left: 10px;">%</span>
          </div>
          <div class="form-item-tip">
            扣量比例范围：0% - 100%，例如：10% 表示扣减10%的转化数量
          </div>
        </el-form-item>
        
        <el-form-item label="扣减策略" prop="deduction_strategy">
          <el-select v-model="form.deduction_strategy" style="width: 100%;">
            <el-option label="随机" value="random">
              <div>
                <div>随机</div>
                <div style="font-size: 12px; color: #909399;">随机选择转化进行扣减，分布更自然</div>
              </div>
            </el-option>
            <el-option label="按比例" value="proportional">
              <div>
                <div>按比例</div>
                <div style="font-size: 12px; color: #909399;">按时间顺序等比例选择转化进行扣减</div>
              </div>
            </el-option>
            <el-option label="轮询" value="round_robin">
              <div>
                <div>轮询</div>
                <div style="font-size: 12px; color: #909399;">轮询选择转化进行扣减</div>
              </div>
            </el-option>
          </el-select>
        </el-form-item>
      </template>
      
      <!-- 按比例扣金额配置 -->
      <el-divider content-position="left">按比例扣金额</el-divider>
      
      <el-form-item label="启用扣金额">
        <el-switch v-model="form.enable_amount_deduction" />
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
              @change="handleAmountRatioChange"
            />
            <span style="margin-left: 10px;">%</span>
          </div>
          <div class="form-item-tip">
            扣金额比例范围：0% - 100%，例如：5% 表示每个转化金额扣减5%
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
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        确定
      </el-button>
    </template>
  </el-dialog>
</template>
```

#### 2.2.2 数据和方法

```javascript
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { 
  createDeductionConfig, 
  updateDeductionConfig,
  getAdvertisers,
  getOffers,
  getPublishers
} from '@/api/deduction'

export default {
  name: 'DeductionConfigDialog',
  props: {
    modelValue: {
      type: Boolean,
      default: false
    },
    config: {
      type: Object,
      default: null
    },
    mode: {
      type: String,
      default: 'add' // 'add' | 'edit'
    }
  },
  emits: ['update:modelValue', 'success'],
  setup(props, { emit }) {
    const formRef = ref(null)
    const submitting = ref(false)
    const targetLoading = ref(false)
    const targetOptions = ref([])
    
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
    
    const visible = computed({
      get: () => props.modelValue,
      set: (val) => emit('update:modelValue', val)
    })
    
    // 表单验证规则
    const rules = {
      level: [
        { required: true, message: '请选择配置层级', trigger: 'change' }
      ],
      target_id: [
        { required: true, message: '请选择配置对象', trigger: 'change' }
      ],
      volume_deduction_ratio: [
        { 
          required: true, 
          validator: (rule, value, callback) => {
            if (form.enable_volume_deduction && (!value || value <= 0)) {
              callback(new Error('启用扣量时，扣量比例必须大于0'))
            } else {
              callback()
            }
          },
          trigger: 'blur'
        }
      ],
      amount_deduction_ratio: [
        { 
          required: true, 
          validator: (rule, value, callback) => {
            if (form.enable_amount_deduction && (!value || value <= 0)) {
              callback(new Error('启用扣金额时，扣金额比例必须大于0'))
            } else {
              callback()
            }
          },
          trigger: 'blur'
        }
      ]
    }
    
    // 监听层级变化，加载对应的选项
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
        
        if (response && response.data) {
          targetOptions.value = response.data.items || response.data
        }
      } catch (error) {
        ElMessage.error('加载配置对象列表失败：' + error.message)
      } finally {
        targetLoading.value = false
      }
    }
    
    // 监听对话框显示，初始化表单
    watch(visible, (val) => {
      if (val) {
        if (props.mode === 'edit' && props.config) {
          // 编辑模式，填充表单
          Object.assign(form, {
            level: props.config.level,
            target_id: props.config.target_id,
            enable_volume_deduction: props.config.enable_volume_deduction,
            volume_deduction_ratio: props.config.volume_deduction_ratio,
            deduction_strategy: props.config.deduction_strategy,
            enable_amount_deduction: props.config.enable_amount_deduction,
            amount_deduction_ratio: props.config.amount_deduction_ratio,
            priority: props.config.priority,
            is_active: props.config.is_active
          })
          handleLevelChange(props.config.level)
        } else {
          // 添加模式，重置表单
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
          handleLevelChange('advertiser')
        }
        
        // 重置表单验证
        if (formRef.value) {
          formRef.value.clearValidate()
        }
      }
    })
    
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
          
          if (props.mode === 'add') {
            await createDeductionConfig(data)
            ElMessage.success('添加成功')
          } else {
            await updateDeductionConfig(props.config.id, data)
            ElMessage.success('更新成功')
          }
          
          emit('success')
          handleClose()
        } catch (error) {
          ElMessage.error((props.mode === 'add' ? '添加' : '更新') + '失败：' + error.message)
        } finally {
          submitting.value = false
        }
      })
    }
    
    // 关闭对话框
    const handleClose = () => {
      visible.value = false
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
    
    return {
      formRef,
      form,
      rules,
      submitting,
      targetLoading,
      targetOptions,
      volumeRatioPercent,
      amountRatioPercent,
      visible,
      handleLevelChange,
      handleSubmit,
      handleClose,
      getLevelLabel
    }
  }
}
</script>

<style scoped>
.form-item-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
```

---

### 2.3 统计报表组件（示例：StatsByTime.vue）

```vue
<template>
  <div class="stats-by-time">
    <!-- 时间范围选择 -->
    <div class="filter-bar">
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        format="YYYY-MM-DD"
        value-format="YYYY-MM-DD"
        style="width: 300px;"
      />
      <el-button type="primary" :icon="Search" @click="handleQuery" style="margin-left: 10px;">
        查询
      </el-button>
      <el-button :icon="Download" @click="handleExport" style="margin-left: 10px;">
        导出Excel
      </el-button>
    </div>
    
    <!-- 总体统计 -->
    <el-card class="summary-card" style="margin-top: 20px;">
      <template #header>
        <span>总体统计</span>
      </template>
      <el-row :gutter="20">
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-label">原始转化数</div>
            <div class="stat-value">{{ summary.original_volume || 0 }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-label">扣减转化数</div>
            <div class="stat-value text-warning">{{ summary.deducted_volume || 0 }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-label">扣减率</div>
            <div class="stat-value text-warning">
              {{ summary.volume_deduction_ratio ? (summary.volume_deduction_ratio * 100).toFixed(2) + '%' : '0%' }}
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-label">最终转化数</div>
            <div class="stat-value text-success">{{ summary.final_volume || 0 }}</div>
          </div>
        </el-col>
      </el-row>
      <el-row :gutter="20" style="margin-top: 20px;">
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-label">原始金额</div>
            <div class="stat-value">${{ (summary.original_amount || 0).toFixed(2) }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-label">扣减金额</div>
            <div class="stat-value text-danger">${{ (summary.deducted_amount || 0).toFixed(2) }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-label">扣减率</div>
            <div class="stat-value text-danger">
              {{ summary.amount_deduction_ratio ? (summary.amount_deduction_ratio * 100).toFixed(2) + '%' : '0%' }}
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-label">最终金额</div>
            <div class="stat-value text-success">${{ (summary.final_amount || 0).toFixed(2) }}</div>
          </div>
        </el-col>
      </el-row>
    </el-card>
    
    <!-- 详细统计表格 -->
    <el-card style="margin-top: 20px;">
      <template #header>
        <span>详细统计</span>
      </template>
      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        style="width: 100%;"
      >
        <el-table-column prop="date" label="日期" width="120" />
        <el-table-column prop="original_volume" label="原始转化数" width="120" align="right" />
        <el-table-column prop="deducted_volume" label="扣减转化数" width="120" align="right">
          <template #default="scope">
            <span class="text-warning">{{ scope.row.deducted_volume || 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="扣减率" width="100" align="right">
          <template #default="scope">
            {{ scope.row.volume_deduction_ratio ? (scope.row.volume_deduction_ratio * 100).toFixed(2) + '%' : '0%' }}
          </template>
        </el-table-column>
        <el-table-column prop="original_amount" label="原始金额" width="120" align="right">
          <template #default="scope">
            ${{ (scope.row.original_amount || 0).toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="deducted_amount" label="扣减金额" width="120" align="right">
          <template #default="scope">
            <span class="text-danger">${{ (scope.row.deducted_amount || 0).toFixed(2) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="扣减率" width="100" align="right">
          <template #default="scope">
            {{ scope.row.amount_deduction_ratio ? (scope.row.amount_deduction_ratio * 100).toFixed(2) + '%' : '0%' }}
          </template>
        </el-table-column>
        <el-table-column prop="final_volume" label="最终转化数" width="120" align="right">
          <template #default="scope">
            <span class="text-success">{{ scope.row.final_volume || 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="final_amount" label="最终金额" width="120" align="right">
          <template #default="scope">
            <span class="text-success">${{ (scope.row.final_amount || 0).toFixed(2) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Download } from '@element-plus/icons-vue'
import { getDeductionStats } from '@/api/deduction'

export default {
  name: 'StatsByTime',
  setup() {
    const loading = ref(false)
    const dateRange = ref([])
    const summary = reactive({
      original_volume: 0,
      deducted_volume: 0,
      final_volume: 0,
      volume_deduction_ratio: 0,
      original_amount: 0,
      deducted_amount: 0,
      final_amount: 0,
      amount_deduction_ratio: 0
    })
    const tableData = ref([])
    
    // 查询统计
    const handleQuery = async () => {
      if (!dateRange.value || dateRange.value.length !== 2) {
        ElMessage.warning('请选择时间范围')
        return
      }
      
      loading.value = true
      try {
        const params = {
          start_date: dateRange.value[0],
          end_date: dateRange.value[1],
          group_by: 'time'
        }
        const response = await getDeductionStats(params)
        summary.original_volume = response.data.summary.original_volume
        summary.deducted_volume = response.data.summary.deducted_volume
        summary.final_volume = response.data.summary.final_volume
        summary.volume_deduction_ratio = response.data.summary.volume_deduction_ratio
        summary.original_amount = response.data.summary.original_amount
        summary.deducted_amount = response.data.summary.deducted_amount
        summary.final_amount = response.data.summary.final_amount
        summary.amount_deduction_ratio = response.data.summary.amount_deduction_ratio
        tableData.value = response.data.items || []
      } catch (error) {
        ElMessage.error('查询统计失败：' + error.message)
      } finally {
        loading.value = false
      }
    }
    
    // 导出Excel
    const handleExport = async () => {
      // 实现导出逻辑
      ElMessage.info('导出功能开发中')
    }
    
    // 初始化：默认查询最近30天
    onMounted(() => {
      const end = new Date()
      const start = new Date()
      start.setDate(start.getDate() - 30)
      dateRange.value = [
        start.toISOString().split('T')[0],
        end.toISOString().split('T')[0]
      ]
      handleQuery()
    })
    
    return {
      loading,
      dateRange,
      summary,
      tableData,
      handleQuery,
      handleExport
    }
  }
}
</script>

<style scoped>
.filter-bar {
  display: flex;
  align-items: center;
}

.stat-item {
  text-align: center;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
}

.text-warning {
  color: #E6A23C;
}

.text-danger {
  color: #F56C6C;
}

.text-success {
  color: #67C23A;
}
</style>
```

---

## 三、API接口设计

### 3.1 API文件（frontend/src/api/deduction.js）

```javascript
import request from '@/utils/request'

/**
 * 获取扣减配置列表
 */
export function getDeductionConfigs(params) {
  return request({
    url: '/api/v1/conversion-deductions',
    method: 'get',
    params
  })
}

/**
 * 创建扣减配置
 */
export function createDeductionConfig(data) {
  return request({
    url: '/api/v1/conversion-deductions',
    method: 'post',
    data
  })
}

/**
 * 更新扣减配置
 */
export function updateDeductionConfig(id, data) {
  return request({
    url: `/api/v1/conversion-deductions/${id}`,
    method: 'put',
    data
  })
}

/**
 * 删除扣减配置
 */
export function deleteDeductionConfig(id) {
  return request({
    url: `/api/v1/conversion-deductions/${id}`,
    method: 'delete'
  })
}

/**
 * 更新扣减配置状态
 */
export function updateDeductionConfigStatus(id, isActive) {
  return request({
    url: `/api/v1/conversion-deductions/${id}/status`,
    method: 'patch',
    data: { is_active: isActive }
  })
}

/**
 * 获取扣减统计
 */
export function getDeductionStats(params) {
  return request({
    url: '/api/v1/conversion-deductions/stats',
    method: 'get',
    params
  })
}

/**
 * 获取扣减日志
 */
export function getDeductionLogs(params) {
  return request({
    url: '/api/v1/conversion-deductions/logs',
    method: 'get',
    params
  })
}

/**
 * 获取广告主列表（用于下拉选择）
 */
export function getAdvertisers(params) {
  return request({
    url: '/api/v1/advertisers',
    method: 'get',
    params
  })
}

/**
 * 获取Offer列表（用于下拉选择）
 */
export function getOffers(params) {
  return request({
    url: '/api/v1/offers',
    method: 'get',
    params
  })
}

/**
 * 获取渠道列表（用于下拉选择）
 */
export function getPublishers(params) {
  return request({
    url: '/api/v1/publishers',
    method: 'get',
    params
  })
}
```

---

## 四、样式设计

### 4.1 主页面样式

```css
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
```

---

## 五、交互流程说明

### 5.1 添加配置流程

1. 用户点击"添加配置"按钮
2. 弹出配置对话框
3. 用户选择配置层级（广告主/Offer/渠道）
4. 系统自动加载对应层级的对象列表
5. 用户选择配置对象
6. 用户配置扣量设置（可选）
   - 启用/禁用扣量
   - 设置扣量比例（0-100%）
   - 选择扣减策略
7. 用户配置扣金额设置（可选）
   - 启用/禁用扣金额
   - 设置扣金额比例（0-100%）
8. 用户设置优先级和状态
9. 用户点击"确定"提交
10. 系统验证表单（至少启用一种扣减方式）
11. 提交成功后关闭对话框，刷新列表

### 5.2 编辑配置流程

1. 用户点击配置列表中的"编辑"按钮
2. 弹出配置对话框，预填充当前配置数据
3. 用户修改配置
4. 用户点击"确定"提交
5. 系统验证并更新配置
6. 提交成功后关闭对话框，刷新列表

### 5.3 查看统计流程

1. 用户切换到"扣减统计报表"标签页
2. 选择时间范围（默认最近30天）
3. 点击"查询"按钮
4. 系统显示总体统计和详细统计表格
5. 用户可以切换不同的分组方式（按时间/按广告主/按Offer/按渠道）
6. 用户可以导出Excel报表

---

## 六、注意事项

### 6.1 表单验证

- 必须选择配置层级和配置对象
- 至少启用一种扣减方式（扣量或扣金额）
- 启用扣量时，扣量比例必须大于0
- 启用扣金额时，扣金额比例必须大于0

### 6.2 数据展示

- 扣量比例和扣金额比例以百分比显示（0-100%）
- 但在提交时转换为小数（0-1）
- 金额显示保留2位小数
- 百分比显示保留2位小数

### 6.3 用户体验

- 配置对象下拉框支持搜索过滤
- 滑块和输入框联动，实时更新
- 扣减策略提供详细说明
- 表单验证错误提示清晰明确
- 操作成功/失败有明确的提示信息

---

## 七、总结

本设计文档提供了完整的CPL扣减系统前端界面设计方案，包括：

1. **页面结构**：主页面布局和组件组织
2. **组件设计**：配置管理组件、配置对话框组件、统计报表组件
3. **API接口**：前端调用的API接口定义
4. **样式设计**：页面和组件的样式定义
5. **交互流程**：用户操作的完整流程说明

该设计确保了：
- 界面清晰直观，易于操作
- 功能完整，覆盖所有需求
- 用户体验良好，交互流畅
- 代码结构清晰，易于维护

