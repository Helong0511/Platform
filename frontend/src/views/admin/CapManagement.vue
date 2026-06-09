<!--
  Cap 上限配置管理页面
  职责：按 Offer/渠道/广告主维度配置日 Cap 与总 Cap，支持筛选、列显隐与 CRUD 弹窗。
-->
<template>
  <!-- 页面主模板 -->
<div class="cap-management">
    <el-card class="page-card">
      <!-- 卡片标题栏 -->
    <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Switch /></el-icon>
            <span class="header-title">Cap管理</span>
          </div>
          <div class="header-right">
            <el-button 
              type="text" 
              :icon="Setting" 
              @click="columnSettingVisible = true"
              style="margin-right: 10px;"
            >
              列设置
            </el-button>
            <el-button type="primary" :icon="Plus" @click="handleAdd">添加Cap配置</el-button>
          </div>
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
      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        style="width: 100%; margin-top: 20px;"
      >
        <el-table-column v-if="columnVisibility.cap_type" prop="cap_type" label="Cap类型" width="150" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.cap_type === 'advertiser_offer' ? 'warning' : 'primary'">
              {{ scope.row.cap_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.offer_name" prop="offer_name" label="Offer" min-width="200" show-overflow-tooltip />
        <el-table-column v-if="columnVisibility.advertiser_name" prop="advertiser_name" label="广告主" width="150" show-overflow-tooltip>
          <template #default="scope">
            <span v-if="scope.row.advertiser_name">{{ scope.row.advertiser_name }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.publisher_name" prop="publisher_name" label="渠道" width="150" show-overflow-tooltip>
          <template #default="scope">
            <span v-if="scope.row.publisher_name">{{ scope.row.publisher_name }}</span>
            <span v-else class="text-info">全部渠道</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.daily_cap" prop="daily_cap" label="每日Cap" width="120" align="right">
          <template #default="scope">
            <span v-if="scope.row.daily_cap">{{ scope.row.daily_cap }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.current_daily_count" prop="current_daily_count" label="当前每日" width="120" align="right">
          <template #default="scope">
            <el-tag :type="scope.row.daily_cap && scope.row.current_daily_count >= scope.row.daily_cap ? 'danger' : 'success'">
              {{ scope.row.current_daily_count }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.total_cap" prop="total_cap" label="总Cap" width="120" align="right">
          <template #default="scope">
            <span v-if="scope.row.total_cap">{{ scope.row.total_cap }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.current_total_count" prop="current_total_count" label="当前总数" width="120" align="right">
          <template #default="scope">
            <el-tag :type="scope.row.total_cap && scope.row.current_total_count >= scope.row.total_cap ? 'danger' : 'success'">
              {{ scope.row.current_total_count }}
            </el-tag>
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
              :label="`${offer.id} - ${offer.offer_name}`"
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

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="cap_type">Cap类型</el-checkbox>
        <el-checkbox label="offer_name" :disabled="true">Offer（固定显示）</el-checkbox>
        <el-checkbox label="advertiser_name">广告主</el-checkbox>
        <el-checkbox label="publisher_name">渠道</el-checkbox>
        <el-checkbox label="daily_cap">每日Cap</el-checkbox>
        <el-checkbox label="current_daily_count">当前每日</el-checkbox>
        <el-checkbox label="total_cap">总Cap</el-checkbox>
        <el-checkbox label="current_total_count">当前总数</el-checkbox>
        <el-checkbox label="is_active">状态</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { ElCheckboxGroup, ElCheckbox } from 'element-plus'
import { Plus, Search, Refresh, Edit, Delete, Switch, Setting } from '@element-plus/icons-vue'
import { useCapColumnVisibility } from '@/composables/useCapColumnVisibility'
import { useCapList } from '@/composables/useCapList'
import { useCapForm } from '@/composables/useCapForm'

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility,
} = useCapColumnVisibility()

const {
  loading,
  filterCapType,
  filterOffer,
  filterPublisher,
  filterActive,
  pagination,
  tableData,
  offerList,
  advertiserList,
  publisherList,
  loadData,
  handleSearch,
  handleReset,
  handleStatusChange,
  handleSizeChange,
  handlePageChange,
  initPage,
} = useCapList()

const {
  submitting,
  dialogVisible,
  isEdit,
  formRef,
  formData,
  formRules,
  handleCapTypeChange,
  handleAdd,
  handleEdit,
  handleDelete,
  handleSubmit,
  handleDialogClose,
} = useCapForm({ loadData })

onMounted(() => {
  loadColumnVisibility()
  initPage()
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

