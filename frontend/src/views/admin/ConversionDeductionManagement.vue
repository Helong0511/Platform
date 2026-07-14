<!--
  管理端 - 转化扣减配置
  @file views/admin/ConversionDeductionManagement.vue
-->
<template>
  <!-- 页面主模板 -->
<div class="conversion-deduction-management">
    <el-card class="page-card">
      <!-- 卡片标题栏 -->
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
              type="link" 
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
        
        <el-select
          v-model="searchForm.advertiser_id"
          placeholder="选择广告主"
          clearable
          filterable
          style="width: 180px; margin-left: 10px;"
          @change="handleSearch"
        >
          <el-option label="全部" :value="null" />
          <el-option
            v-for="adv in advertiserList"
            :key="adv.id"
            :label="adv.advertiser_name"
            :value="adv.id"
          />
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
        
        <el-table-column v-if="columnVisibility.advertiser_name" prop="advertiser_name" label="广告主" min-width="180" show-overflow-tooltip />
        
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
        <el-checkbox label="advertiser_name">广告主</el-checkbox>
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
import { onMounted } from 'vue'
import { ElCheckboxGroup, ElCheckbox } from 'element-plus'
import { Search, Refresh, Plus, Setting, Remove, Money, Close, InfoFilled, Check, Delete, Download } from '@element-plus/icons-vue'
import { useConversionDeductionColumnVisibility } from '@/composables/useConversionDeductionColumnVisibility'
import { useConversionDeductionList } from '@/composables/useConversionDeductionList'
import { useConversionDeductionForm } from '@/composables/useConversionDeductionForm'
import { getLevelLabel, getLevelTagType, getStrategyLabel } from '@/utils/conversionDeductionFormat'

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility,
} = useConversionDeductionColumnVisibility()

const {
  loading,
  tableData,
  selectedConfigs,
  advertiserList,
  searchForm,
  pagination,
  fetchData,
  handleSearch,
  handleReset,
  handleStatusChange,
  handleSelectionChange,
  handleBatchEnable,
  handleBatchDisable,
  handleBatchDelete,
  handleDelete,
  handleExport,
  handlePageChange,
  handleSizeChange,
  initPage,
} = useConversionDeductionList()

const {
  dialogVisible,
  dialogMode,
  submitting,
  targetLoading,
  targetOptions,
  formRef,
  form,
  rules,
  volumeRatioPercent,
  amountRatioPercent,
  handleLevelChange,
  handleAdd,
  handleEdit,
  handleCopy,
  handleDialogClose,
  handleSubmit,
} = useConversionDeductionForm({ fetchData })

onMounted(() => {
  loadColumnVisibility()
  initPage()
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


