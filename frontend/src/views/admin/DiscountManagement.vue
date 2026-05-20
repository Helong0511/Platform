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
          placeholder="请选择扣量类型"
          clearable
          style="width: 160px; min-width: 160px;"
          @change="handleSearch"
        >
          <el-option label="全部" :value="null" />
          <el-option label="offer" value="offer" />
          <el-option label="channel" value="channel" />
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
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 20px; margin-bottom: 10px;">
        <span style="font-weight: 600;">扣量配置列表</span>
        <el-button 
          type="text" 
          :icon="Setting" 
          @click="columnSettingVisible = true"
        >
          列设置
        </el-button>
      </div>
      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        style="width: 100%;"
      >
        <el-table-column v-if="columnVisibility.discount_type" prop="discount_type" label="扣量类型" width="120" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.discount_type === 'offer' ? 'warning' : 'primary'">
              {{ scope.row.discount_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.offer_name" prop="offer_name" label="Offer" min-width="200" show-overflow-tooltip>
          <template #default="scope">
            <span v-if="scope.row.offer_name">{{ scope.row.offer_name }}</span>
            <span v-else class="text-info">渠道级别</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.publisher_name" prop="publisher_name" label="渠道" min-width="150" show-overflow-tooltip />
        <el-table-column v-if="columnVisibility.discount_ratio" prop="discount_ratio" label="扣量比例" width="120" align="right">
          <template #default="scope">
            <el-tag type="danger">{{ scope.row.discount_ratio }}%</el-tag>
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
        <el-table-column v-if="columnVisibility.created_at" prop="created_at" label="创建时间" width="180">
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
      :append-to-body="true"
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="120px"
      >
        <el-form-item label="扣量类型" prop="discount_type">
          <el-select 
            v-model="formData.discount_type" 
            style="width: 100%;" 
            @change="handleDiscountTypeChange"
          >
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
              :label="`${offer.id} - ${offer.offer_name}`"
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

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="discount_type">扣量类型</el-checkbox>
        <el-checkbox label="offer_name">Offer</el-checkbox>
        <el-checkbox label="publisher_name">渠道</el-checkbox>
        <el-checkbox label="discount_ratio">扣量比例</el-checkbox>
        <el-checkbox label="is_active">状态</el-checkbox>
        <el-checkbox label="created_at">创建时间</el-checkbox>
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
import { Plus, Search, Refresh, Edit, Delete, Discount, Setting } from '@element-plus/icons-vue'
import { formatDate } from '@/utils/date'
import { useDiscountColumnVisibility } from '@/composables/useDiscountColumnVisibility'
import { useDiscountList } from '@/composables/useDiscountList'
import { useDiscountForm } from '@/composables/useDiscountForm'

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility,
} = useDiscountColumnVisibility()

const {
  loading,
  filterDiscountType,
  filterOffer,
  filterPublisher,
  filterActive,
  pagination,
  tableData,
  offerList,
  publisherList,
  loadData,
  handleSearch,
  handleReset,
  handleStatusChange,
  handleSizeChange,
  handlePageChange,
  initPage,
} = useDiscountList()

const {
  submitting,
  dialogVisible,
  isEdit,
  formRef,
  formData,
  formRules,
  handleDiscountTypeChange,
  handleAdd,
  handleEdit,
  handleDelete,
  handleSubmit,
  handleDialogClose,
} = useDiscountForm({ loadData })

onMounted(() => {
  loadColumnVisibility()
  initPage()
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

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}
</style>

