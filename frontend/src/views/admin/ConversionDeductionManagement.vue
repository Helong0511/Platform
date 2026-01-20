<template>
  <div class="conversion-deduction-management">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Setting /></el-icon>
            <span class="header-title">转化扣减配置管理</span>
          </div>
          <div class="header-right">
            <div class="batch-actions" v-if="selectedConfigs.length > 0">
              <el-button 
                type="success" 
                :icon="Check" 
                @click="handleBatchEnable"
                :disabled="loading"
              >
                批量启用 ({{ selectedConfigs.length }})
              </el-button>
              <el-button 
                type="warning" 
                :icon="Close" 
                @click="handleBatchDisable"
                :disabled="loading"
              >
                批量禁用 ({{ selectedConfigs.length }})
              </el-button>
              <el-button 
                type="danger" 
                :icon="Delete" 
                @click="handleBatchDelete"
                :disabled="loading"
              >
                批量删除 ({{ selectedConfigs.length }})
              </el-button>
            </div>
            <el-button 
              type="text" 
              :icon="Setting" 
              @click="columnSettingVisible = true"
              style="margin-right: 10px;"
            >
              列设置
            </el-button>
            <el-button type="primary" :icon="Download" @click="handleExport" :disabled="loading">导出配置</el-button>
            <el-button type="primary" :icon="Plus" @click="handleAdd">添加配置</el-button>
          </div>
        </div>
      </template>

      <!-- 功能说明卡片 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 20px;"
      >
        <template #title>
          <div style="line-height: 1.8;">
            <div style="font-weight: 600; margin-bottom: 8px;">扣减系统说明：</div>
            <div style="margin-left: 20px;">
              <div style="margin-bottom: 6px;">
                <strong style="color: #E6A23C;">扣量（Volume Deduction）</strong>：
                减少转化数量，被扣减的转化<strong style="color: #F56C6C;">不会保存到数据库</strong>，下游渠道<strong style="color: #F56C6C;">无法看到</strong>这些转化。
                扣量是"全有或全无"的操作，在24小时统计窗口内动态计算，确保达到目标比例。
              </div>
              <div>
                <strong style="color: #F56C6C;">扣金额（Amount Deduction）</strong>：
                减少转化金额，转化<strong style="color: #67C23A;">仍然保存到数据库</strong>，但金额会按比例减少，下游可以看到转化但<strong style="color: #F56C6C;">金额已扣减</strong>。
                扣金额是固定比例操作，直接应用于每个转化。
              </div>
              <div style="margin-top: 8px; font-size: 12px; color: #909399;">
                <strong>配置优先级</strong>：Offer级别 > 广告主级别 > 渠道级别（数字越大优先级越高）
              </div>
            </div>
          </div>
        </template>
      </el-alert>

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
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column v-if="columnVisibility.id" prop="id" label="ID" width="80" align="center" />
        
        <el-table-column v-if="columnVisibility.level" prop="level" label="层级" width="100" align="center">
          <template #default="scope">
            <el-tag :type="getLevelTagType(scope.row.level)">
              {{ getLevelLabel(scope.row.level) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column v-if="columnVisibility.target_name" prop="target_name" label="配置对象" min-width="200" show-overflow-tooltip />
        
        <el-table-column v-if="columnVisibility.volume_deduction" label="扣量配置" width="180" align="center">
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
        
        <el-table-column v-if="columnVisibility.amount_deduction" label="扣金额配置" width="150" align="center">
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
        
        <el-table-column v-if="columnVisibility.priority" prop="priority" label="优先级" width="100" align="center" />
        
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
        
        <el-table-column label="操作" width="200" align="center" fixed="right">
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
              type="info"
              link
              size="small"
              @click="handleCopy(scope.row)"
            >
              复制
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

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="id" :disabled="true">ID（固定显示）</el-checkbox>
        <el-checkbox label="level">层级</el-checkbox>
        <el-checkbox label="target_name" :disabled="true">配置对象（固定显示）</el-checkbox>
        <el-checkbox label="volume_deduction">扣量配置</el-checkbox>
        <el-checkbox label="amount_deduction">扣金额配置</el-checkbox>
        <el-checkbox label="priority">优先级</el-checkbox>
        <el-checkbox label="is_active">状态</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>

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
            <div style="line-height: 1.6;">
              <strong>扣量说明：</strong>
              <ul style="margin: 4px 0 0 20px; padding: 0;">
                <li>扣量是"全有或全无"的操作，一个转化要么被扣量（数量变为0），要么不被扣量（数量保持为1）</li>
                <li>被扣量的转化<strong style="color: #F56C6C;">不会保存到主转化表</strong>，下游渠道<strong style="color: #F56C6C;">无法看到</strong></li>
                <li>扣量比例是<strong>动态计算</strong>的，系统会在24小时统计窗口内实时统计，确保达到目标比例</li>
                <li>例如：配置10%扣量，在24小时内100个转化中，系统会确保扣减10个转化</li>
              </ul>
            </div>
          </div>
        </el-form-item>
        
        <template v-if="form.enable_volume_deduction">
          <el-form-item 
            label="扣量比例" 
            prop="volume_deduction_ratio"
            :rules="[
              { required: true, message: '请设置扣量比例', trigger: 'blur' },
              { type: 'number', min: 0.01, max: 100, message: '扣量比例必须在0.01%到100%之间', trigger: 'blur' }
            ]"
          >
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
              <strong>扣量比例说明：</strong>
              <ul style="margin: 4px 0 0 20px; padding: 0; line-height: 1.6;">
                <li>范围：0% - 100%</li>
                <li>示例：10% 表示在24小时统计窗口内，扣减10%的转化数量</li>
                <li>计算方式：系统统计最近24小时内的转化，动态计算是否扣减当前转化</li>
                <li>结果：被扣减的转化<strong style="color: #F56C6C;">不会保存到数据库</strong>，下游渠道<strong style="color: #F56C6C;">完全看不到</strong></li>
              </ul>
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
              <strong>扣减策略说明：</strong>
              <ul style="margin: 4px 0 0 20px; padding: 0; line-height: 1.6;">
                <li><strong>随机（random）</strong>：随机选择转化进行扣减，分布更自然，难以预测。使用概率算法确保在24小时窗口内达到目标比例。</li>
                <li><strong>按比例（proportional）</strong>：按固定间隔扣量，如每10个扣1个（10%扣量时）。按时间顺序等比例选择转化。</li>
                <li><strong>轮询（round_robin）</strong>：轮询方式扣量，按固定间隔循环。例如10%扣量时，每10个转化扣1个。</li>
              </ul>
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
            <div style="line-height: 1.6;">
              <strong>扣金额说明：</strong>
              <ul style="margin: 4px 0 0 20px; padding: 0;">
                <li>扣金额是<strong>固定比例操作</strong>，直接应用于每个转化</li>
                <li>转化<strong style="color: #67C23A;">仍然保存到数据库</strong>，下游渠道可以看到转化记录</li>
                <li>但最终支付给下游的金额会<strong style="color: #F56C6C;">按比例减少</strong></li>
                <li>例如：配置5%扣金额，转化金额$100，扣减后支付$95给下游</li>
              </ul>
            </div>
          </div>
        </el-form-item>
        
        <template v-if="form.enable_amount_deduction">
          <el-form-item 
            label="扣金额比例" 
            prop="amount_deduction_ratio"
            :rules="[
              { required: true, message: '请设置扣金额比例', trigger: 'blur' },
              { type: 'number', min: 0.01, max: 100, message: '扣金额比例必须在0.01%到100%之间', trigger: 'blur' }
            ]"
          >
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
              <strong>扣金额比例说明：</strong>
              <ul style="margin: 4px 0 0 20px; padding: 0; line-height: 1.6;">
                <li>范围：0% - 100%</li>
                <li>示例：5% 表示每个转化金额扣减5%</li>
                <li>计算方式：<code>最终金额 = 原始金额 × (1 - 扣金额比例)</code></li>
                <li>示例计算：原始金额$100，扣金额比例5%，最终金额 = $100 × (1 - 0.05) = $95</li>
                <li>结果：转化<strong style="color: #67C23A;">仍然保存到数据库</strong>，但支付给下游的金额<strong style="color: #F56C6C;">已扣减</strong></li>
              </ul>
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
            <strong>优先级说明：</strong>
            <ul style="margin: 4px 0 0 20px; padding: 0; line-height: 1.6;">
              <li>范围：0 - 100，数字越大优先级越高</li>
              <li><strong>配置层级优先级</strong>（固定）：Offer级别 > 广告主级别 > 渠道级别</li>
              <li><strong>同层级优先级</strong>：相同层级时，优先级数字大的配置生效</li>
              <li>示例：两个Offer级别配置，优先级分别为10和20，则优先级20的配置生效</li>
            </ul>
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
import { ElMessage, ElMessageBox, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus'
import { Search, Refresh, Plus, Setting, Remove, Money, Close, InfoFilled, Check, Delete, Download } from '@element-plus/icons-vue'
import {
  getDeductionConfigs,
  createDeductionConfig,
  updateDeductionConfig,
  deleteDeductionConfig,
  updateDeductionConfigStatus,
  batchUpdateDeductionConfigStatus,
  batchDeleteDeductionConfigs
} from '@/api/deduction'
import { getAdvertisers } from '@/api/advertiser'
import { getOffers } from '@/api/offer'
import { getPublishers } from '@/api/publisher'

const loading = ref(false)
const tableData = ref([])
const columnSettingVisible = ref(false)
const selectedConfigs = ref([])
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

// 列显示状态（默认全部显示）
const getDefaultColumnVisibility = () => ({
  id: true,  // 固定显示
  level: true,
  target_name: true,  // 固定显示
  volume_deduction: true,
  amount_deduction: true,
  priority: true,
  is_active: true
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
    const saved = localStorage.getItem('conversionDeductionManagement_columnVisibility')
    if (saved) {
      const savedVisibility = JSON.parse(saved)
      // 合并保存的设置和默认设置
      Object.assign(columnVisibility, getDefaultColumnVisibility(), savedVisibility)
      // 确保固定列始终显示
      columnVisibility.id = true
      columnVisibility.target_name = true
    }
  } catch (error) {
    logger.error('加载列显示设置失败:', error)
  }
}

// 保存列显示设置到localStorage
const saveColumnVisibility = () => {
  try {
    // 只保存可调整的列，不保存固定列
    const toSave = {
      level: columnVisibility.level,
      volume_deduction: columnVisibility.volume_deduction,
      amount_deduction: columnVisibility.amount_deduction,
      priority: columnVisibility.priority,
      is_active: columnVisibility.is_active
    }
    localStorage.setItem('conversionDeductionManagement_columnVisibility', JSON.stringify(toSave))
    columnSettingVisible.value = false
    ElMessage.success('列显示设置已保存')
  } catch (error) {
    logger.error('保存列显示设置失败:', error)
    ElMessage.error('保存设置失败')
  }
}

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
  ],
  volume_deduction_ratio: [
    { 
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
    // response已经是标准分页格式，直接使用data和total字段
    tableData.value = response.data || []
    pagination.total = response.total || 0
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

// 复制配置
const handleCopy = (row) => {
  dialogMode.value = 'add'
  currentConfig.value = null
  
  // 复制配置数据，但清空ID和创建时间，默认禁用状态
  Object.assign(form, {
    level: row.level,
    target_id: row.target_id,
    enable_volume_deduction: row.enable_volume_deduction,
    volume_deduction_ratio: row.volume_deduction_ratio,
    deduction_strategy: row.deduction_strategy,
    enable_amount_deduction: row.enable_amount_deduction,
    amount_deduction_ratio: row.amount_deduction_ratio,
    priority: row.priority,
    is_active: false // 复制时默认禁用，需要手动启用
  })
  
  // 加载配置对象选项
  handleLevelChange(row.level)
  
  dialogVisible.value = true
  ElMessage.info('已复制配置，请检查并修改后保存（默认状态为禁用）')
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

// 批量选择
const handleSelectionChange = (selection) => {
  selectedConfigs.value = selection
}

// 批量启用
const handleBatchEnable = async () => {
  if (selectedConfigs.value.length === 0) {
    ElMessage.warning('请先选择要启用的配置')
    return
  }
  
  try {
    await ElMessageBox.confirm(
      `确定要启用选中的 ${selectedConfigs.value.length} 个配置吗？`,
      '确认批量启用',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    loading.value = true
    const configIds = selectedConfigs.value.map(item => item.id)
    // batchUpdateDeductionConfigStatus使用returnDataOnly: true，成功时直接返回数据，失败时抛出异常
    const response = await batchUpdateDeductionConfigStatus({
      config_ids: configIds,
      is_active: true
    })
    
    // 如果执行到这里，说明操作成功（失败会抛出异常）
    ElMessage.success(`成功启用 ${response.updated_count || configIds.length} 个配置`)
    selectedConfigs.value = []
    fetchData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量启用失败：' + (error.message || '未知错误'))
    }
  } finally {
    loading.value = false
  }
}

// 批量禁用
const handleBatchDisable = async () => {
  if (selectedConfigs.value.length === 0) {
    ElMessage.warning('请先选择要禁用的配置')
    return
  }
  
  try {
    await ElMessageBox.confirm(
      `确定要禁用选中的 ${selectedConfigs.value.length} 个配置吗？`,
      '确认批量禁用',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    loading.value = true
    const configIds = selectedConfigs.value.map(item => item.id)
    // batchUpdateDeductionConfigStatus使用returnDataOnly: true，成功时直接返回数据，失败时抛出异常
    const response = await batchUpdateDeductionConfigStatus({
      config_ids: configIds,
      is_active: false
    })
    
    // 如果执行到这里，说明操作成功（失败会抛出异常）
    ElMessage.success(`成功禁用 ${response.updated_count || configIds.length} 个配置`)
    selectedConfigs.value = []
    fetchData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量禁用失败：' + (error.message || '未知错误'))
    }
  } finally {
    loading.value = false
  }
}

// 批量删除
const handleBatchDelete = async () => {
  if (selectedConfigs.value.length === 0) {
    ElMessage.warning('请先选择要删除的配置')
    return
  }
  
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedConfigs.value.length} 个配置吗？此操作不可恢复！`,
      '确认批量删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    loading.value = true
    const configIds = selectedConfigs.value.map(item => item.id)
    // batchDeleteDeductionConfigs使用returnDataOnly: true，成功时直接返回数据，失败时抛出异常
    const response = await batchDeleteDeductionConfigs({
      config_ids: configIds
    })
    
    // 如果执行到这里，说明操作成功（失败会抛出异常）
    ElMessage.success(`成功删除 ${response.deleted_count || configIds.length} 个配置`)
    selectedConfigs.value = []
    fetchData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量删除失败：' + (error.message || '未知错误'))
    }
  } finally {
    loading.value = false
  }
}

// 层级变化
const handleLevelChange = async (level) => {
  form.target_id = null
  targetOptions.value = []
  
  if (!level) return
  
  targetLoading.value = true
  try {
    let allItems = []
    let page = 1
    const pageSize = 100 // 后端最大限制
    let hasMore = true
    
    // 分页加载所有数据
    while (hasMore) {
      let response
      if (level === 'advertiser') {
        response = await getAdvertisers({ page, page_size: pageSize })
      } else if (level === 'offer') {
        response = await getOffers({ page, page_size: pageSize })
      } else if (level === 'publisher') {
        response = await getPublishers({ page, page_size: pageSize })
      }
      
      // response已经是标准分页格式，直接使用data和total字段
      const items = response.data || []
      allItems = allItems.concat(items)
      
      // 检查是否还有更多数据
      const total = response.total || 0
      hasMore = allItems.length < total && items.length > 0
      page++
    }
    
    // 转换为选项格式（Offer按ID排序）
    const sortedItems = level === 'offer'
      ? allItems.slice().sort((a, b) => a.id - b.id)
      : allItems
    targetOptions.value = sortedItems.map(item => ({
      id: item.id,
      name: level === 'offer'
        ? `${item.id} - ${item.offer_name}`
        : (item.advertiser_name || item.offer_name || item.publisher_name)
    }))
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
      // 显示详细的错误信息
      const errorMsg = error.response?.data?.detail || error.response?.data?.message || error.message || '未知错误'
      ElMessage.error((dialogMode.value === 'add' ? '添加' : '更新') + '失败：' + errorMsg)
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
  // 确保page_size不超过后端最大限制
  pagination.page_size = Math.min(size, 100)
  pagination.page = 1
  fetchData()
}

// 导出配置
const handleExport = async () => {
  try {
    loading.value = true
    // 构建导出参数（使用当前筛选条件）
    const params = new URLSearchParams()
    if (searchForm.keyword) {
      params.append('keyword', searchForm.keyword)
    }
    if (searchForm.level) {
      params.append('level', searchForm.level)
    }
    if (searchForm.is_active !== null && searchForm.is_active !== undefined) {
      params.append('is_active', searchForm.is_active.toString())
    }
    
    // 使用window.open下载文件
    const url = `/api/v1/conversion-deductions/export?${params.toString()}`
    window.open(url, '_blank')
    
    ElMessage.success('导出请求已发送，请稍候...')
  } catch (error) {
    ElMessage.error('导出失败：' + (error.message || '未知错误'))
  } finally {
    loading.value = false
  }
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
  // 加载列显示设置
  loadColumnVisibility()
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

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.batch-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-right: 10px;
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


