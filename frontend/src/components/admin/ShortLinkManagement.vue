<!--
  短链接管理内嵌组件
  @file components/admin/ShortLinkManagement.vue
-->
<template>
  <!-- 页面主模板 -->
<div class="short-link-management">
    <!-- 统计卡片 -->
    <div class="stats-cards">
      <el-card class="stat-card">
        <el-statistic title="总链接数" :value="stats.total_links" />
      </el-card>
      <el-card class="stat-card">
        <el-statistic title="总点击次数" :value="stats.total_clicks" />
      </el-card>
      <el-card class="stat-card">
        <el-statistic title="活跃链接" :value="stats.active_links" />
      </el-card>
      <el-card class="stat-card">
        <el-statistic title="过期链接" :value="stats.expired_links" />
      </el-card>
    </div>

    <!-- 操作栏 -->
    <div class="action-bar">
      <el-button type="primary" @click="handleCreate" :icon="Plus">创建短链接</el-button>
      <el-button 
        type="link" 
        :icon="Setting" 
        @click="columnSettingVisible = true"
        style="margin-left: 10px;"
      >
        列设置
      </el-button>
      <div class="search-bar">
        <el-input
          v-model="filters.search"
          placeholder="搜索链接（标题、URL、代码）"
          clearable
          style="width: 300px;"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button @click="handleSearch" :icon="Search">搜索</el-button>
      </div>
    </div>

    <!-- 表格 -->
    <el-table
      v-loading="loading"
      :data="links"
      border
      stripe
      style="width: 100%"
    >
      <el-table-column v-if="columnVisibility.id" prop="id" label="ID" width="80" align="center" />
      <el-table-column v-if="columnVisibility.short_code" prop="short_code" label="短链接代码" width="100" show-overflow-tooltip>
        <template #default="scope">
          <el-tag type="primary">{{ scope.row.short_code }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="columnVisibility.short_url" prop="short_url" label="短链接" width="300" show-overflow-tooltip>
        <template #default="scope">
          <el-link :href="scope.row.short_url" target="_blank" rel="noopener noreferrer" type="primary">
            {{ scope.row.short_url }}
          </el-link>
          <el-button
            text
            type="primary"
            :icon="DocumentCopy"
            @click="copyToClipboard(scope.row.short_url)"
            style="margin-left: 8px;"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="columnVisibility.original_url" prop="original_url" label="原始URL" min-width="350" show-overflow-tooltip />
      <el-table-column v-if="columnVisibility.title" prop="title" label="标题" width="180" show-overflow-tooltip>
        <template #default="scope">
          <span v-if="scope.row.title">{{ scope.row.title }}</span>
          <span v-else style="color: #909399;">-</span>
        </template>
      </el-table-column>
      <el-table-column v-if="columnVisibility.description" prop="description" label="描述" min-width="250" show-overflow-tooltip>
        <template #default="scope">
          <span v-if="scope.row.description">{{ scope.row.description }}</span>
          <span v-else style="color: #909399;">-</span>
        </template>
      </el-table-column>
      <el-table-column v-if="columnVisibility.offer_id" prop="offer_id" label="关联Offer" width="180" show-overflow-tooltip>
        <template #default="scope">
          <el-tag v-if="scope.row.offer_id" type="info">
            {{ getOfferName(scope.row.offer_id) || `ID: ${scope.row.offer_id}` }}
          </el-tag>
          <span v-else style="color: #909399;">-</span>
        </template>
      </el-table-column>
      <el-table-column v-if="columnVisibility.channel_id" prop="channel_id" label="渠道" width="80" show-overflow-tooltip>
        <template #default="scope">
          <el-tag v-if="scope.row.channel_id" type="success">
            {{ scope.row.channel_name || getChannelName(scope.row.channel_id) || `ID: ${scope.row.channel_id}` }}
          </el-tag>
          <span v-else style="color: #909399;">-</span>
        </template>
      </el-table-column>
      <el-table-column v-if="columnVisibility.creator_name" prop="creator_name" label="创建者" width="120" show-overflow-tooltip>
        <template #default="scope">
          <span v-if="scope.row.creator_name">{{ scope.row.creator_name }}</span>
          <el-tag v-else type="info" size="small">未知</el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="columnVisibility.click_count" prop="click_count" label="点击次数" width="100" align="center">
        <template #default="scope">
          <el-tag type="success">{{ scope.row.click_count }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="columnVisibility.show_count" prop="show_count" label="展示次数" width="100" align="center">
        <template #default="scope">
          <el-tag type="info">{{ scope.row.show_count }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="columnVisibility.expires_at" prop="expires_at" label="过期时间" width="180" align="center">
        <template #default="scope">
          <span v-if="scope.row.expires_at">{{ formatDate(scope.row.expires_at) }}</span>
          <el-tag v-else type="info" size="small">永不过期</el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="columnVisibility.is_active" prop="is_active" label="激活" width="90" align="center">
        <template #default="scope">
          <el-switch
            v-model="scope.row.is_active"
            @change="handleToggleActive(scope.row)"
            :active-text="scope.row.is_active ? '激活' : ''"
            :inactive-text="!scope.row.is_active ? '禁用' : ''"
            aria-label="切换激活状态"
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
          <el-button type="primary" size="small" @click="handleEdit(scope.row)">编辑</el-button>
          <el-button type="danger" size="small" @click="handleDelete(scope.row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination">
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

    <!-- 创建/编辑对话框 -->
    <ShortLinkFormDialog
      v-model="dialogVisible"
      :form-data="formData"
      :form-rules="formRules"
      :is-edit="isEdit"
      :offer-list="offerList"
      :channel-list="channelList"
      :generating-code="generatingCode"
      :saving="saving"
      @save="handleSave"
      @generate-code="handleGenerateCode"
      @close="handleDialogClose"
    />

    <!-- 列设置对话框 -->
    <!-- 弹窗 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="id">ID</el-checkbox>
        <el-checkbox label="short_code" :disabled="true">短代码（固定显示）</el-checkbox>
        <el-checkbox label="short_url" :disabled="true">短链接（固定显示）</el-checkbox>
        <el-checkbox label="original_url">原始URL</el-checkbox>
        <el-checkbox label="title">标题</el-checkbox>
        <el-checkbox label="description">描述</el-checkbox>
        <el-checkbox label="offer_id">Offer</el-checkbox>
        <el-checkbox label="channel_id">渠道</el-checkbox>
        <el-checkbox label="creator_name">创建者</el-checkbox>
        <el-checkbox label="click_count">点击数</el-checkbox>
        <el-checkbox label="show_count">展示次数</el-checkbox>
        <el-checkbox label="expires_at">过期时间</el-checkbox>
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
import { onMounted } from 'vue';
import { ElStatistic, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus';
import { Plus, Search, DocumentCopy, Setting } from '@element-plus/icons-vue';
import { useShortLinkColumnVisibility } from '../../composables/useShortLinkColumnVisibility';
import { useShortLinkList } from '../../composables/useShortLinkList';
import { useShortLinkForm } from '../../composables/useShortLinkForm';
import { copyToClipboard } from '../../utils/clipboard';
import { formatDate } from '../../utils/dateFormat';
import ShortLinkFormDialog from './ShortLinkFormDialog.vue';

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility,
} = useShortLinkColumnVisibility();

const {
  loading,
  links,
  offerList,
  channelList,
  stats,
  filters,
  pagination,
  refreshListAndStats,
  getOfferName,
  getChannelName,
  handleSearch,
  handleSizeChange,
  handlePageChange,
  handleToggleActive,
  bindRouteSearchWatch,
  initPage,
} = useShortLinkList();

const {
  saving,
  generatingCode,
  dialogVisible,
  isEdit,
  formData,
  formRules,
  handleCreate,
  handleEdit,
  handleSave,
  handleDelete,
  handleGenerateCode,
  handleDialogClose,
} = useShortLinkForm({ refreshListAndStats });

bindRouteSearchWatch();

onMounted(async () => {
  loadColumnVisibility();
  await initPage();
});
</script>

<style scoped>
.short-link-management {
  padding: 20px;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
}

.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.search-bar {
  display: flex;
  gap: 10px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.form-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}
</style>

