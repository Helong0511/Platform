<template>
  <el-dialog
    v-model="visible"
    title="通知记录"
    :width="isMobile ? '95%' : '1200px'"
    :close-on-click-modal="false"
    @close="handleClose"
    append-to-body
  >
    <div class="notification-records-content">
      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-form :inline="true" :model="filters">
          <el-form-item label="状态">
            <el-select 
              v-model="filters.notification_status" 
              clearable 
              placeholder="全部" 
              style="width: 120px"
            >
              <el-option label="已发送" value="sent" />
              <el-option label="失败" value="failed" />
              <el-option label="待发送" value="pending" />
            </el-select>
          </el-form-item>
          <el-form-item label="渠道">
            <el-select 
              v-model="filters.notification_channel" 
              clearable 
              placeholder="全部" 
              style="width: 120px"
            >
              <el-option label="Telegram" value="telegram" />
              <el-option label="邮箱" value="email" />
              <el-option label="短信" value="sms" />
              <el-option label="Webhook" value="webhook" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleSearch">查询</el-button>
            <el-button @click="handleReset">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 表格 -->
      <el-table
        v-loading="loading"
        :data="records"
        border
        stripe
        :max-height="500"
      >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="conversion_id" label="转化ID" width="100">
          <template #default="scope">
            <span v-if="scope.row.conversion_id">{{ scope.row.conversion_id }}</span>
            <el-tag v-else type="info" size="small">汇总通知</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="notification_type" label="类型" width="100">
          <template #default="scope">
            <el-tag :type="getTypeTagType(scope.row.notification_type)" size="small">
              {{ getTypeLabel(scope.row.notification_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="notification_channel" label="渠道" width="100">
          <template #default="scope">
            <el-tag :type="getChannelTagType(scope.row.notification_channel)" size="small">
              {{ getChannelLabel(scope.row.notification_channel) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="notification_status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="getStatusTagType(scope.row.notification_status)" size="small">
              {{ getStatusLabel(scope.row.notification_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="auto_notify" label="通知方式" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.auto_notify ? 'success' : 'info'" size="small">
              {{ scope.row.auto_notify ? '自动' : '手动' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="notification_message" label="消息内容" min-width="200" show-overflow-tooltip />
        <el-table-column prop="error_message" label="错误信息" min-width="150" show-overflow-tooltip v-if="hasErrorMessages" />
        <el-table-column prop="postback_url" label="Postback URL" min-width="150" show-overflow-tooltip v-if="hasPostbackUrls">
          <template #default="scope">
            <el-link v-if="scope.row.postback_url" :href="scope.row.postback_url" target="_blank" type="primary">
              {{ scope.row.postback_url.length > 50 ? scope.row.postback_url.substring(0, 50) + '...' : scope.row.postback_url }}
            </el-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
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
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue';
import { getNotificationRecords } from '../../api/notification';
import { useDevice } from '../../composables/useDevice';
import { logger } from '../../utils/logger';
import { formatDate as formatDateWithTimezone } from '../../utils/dateFormat';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  conversionId: { type: Number, default: null },
  clientId: { type: Number, default: null },
  productId: { type: Number, default: null },
  publisherId: { type: Number, default: null }
});

const emit = defineEmits(['update:modelValue']);

const { isMobile } = useDevice();
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
});

const loading = ref(false);
const records = ref([]);

const filters = reactive({
  notification_status: null,
  notification_channel: null
});

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
});

const loadRecords = async () => {
  loading.value = true;
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...filters
    };
    // 优先使用 conversionId（最精确的过滤）
    if (props.conversionId) {
      params.conversion_id = props.conversionId;
    } else {
      // 如果没有 conversionId，使用其他过滤条件
      if (props.clientId) params.client_id = props.clientId;
      if (props.productId) params.product_id = props.productId;
      if (props.publisherId) params.publisher_id = props.publisherId;
    }
    
    const result = await getNotificationRecords(params);
    records.value = result.data || [];
    pagination.total = result.total || 0;
  } catch (error) {
    logger.error('加载通知记录失败:', error);
  } finally {
    loading.value = false;
  }
};

const handleSearch = () => {
  pagination.page = 1;
  loadRecords();
};

const handleReset = () => {
  filters.notification_status = null;
  filters.notification_channel = null;
  handleSearch();
};

const handleSizeChange = (size) => {
  pagination.pageSize = size;
  pagination.page = 1;  // 分页大小变化时重置到第一页
  loadRecords();
};

const handlePageChange = (page) => {
  pagination.page = page;
  loadRecords();
};

const handleClose = () => {
  visible.value = false;
};

const formatDate = (dateString) => {
  return formatDateWithTimezone(dateString);
};

const getChannelLabel = (channel) => {
  const labels = {
    telegram: 'Telegram',
    email: '邮箱',
    sms: '短信',
    webhook: 'Webhook'
  };
  return labels[channel] || channel;
};

const getChannelTagType = (channel) => {
  const types = {
    telegram: 'primary',
    email: 'success',
    sms: 'warning'
  };
  return types[channel] || 'info';
};

const getStatusLabel = (status) => {
  const labels = {
    sent: '已发送',
    failed: '失败',
    pending: '待发送'
  };
  return labels[status] || status;
};

const getStatusTagType = (status) => {
  const types = {
    sent: 'success',
    failed: 'danger',
    pending: 'warning'
  };
  return types[status] || 'info';
};

const getTypeLabel = (type) => {
  const labels = {
    conversion: '转化通知',
    high_value: '高价值通知',
    error: '错误通知',
    forward: '转发通知',
    summary_hourly: '每小时汇总',
    summary_daily: '每天汇总'
  };
  return labels[type] || type || '-';
};

const getTypeTagType = (type) => {
  const types = {
    conversion: 'primary',
    high_value: 'warning',
    error: 'danger',
    forward: 'info',
    summary_hourly: 'success',
    summary_daily: 'success'
  };
  return types[type] || 'info';
};

// 计算是否显示错误信息列（如果有任何记录有错误信息）
const hasErrorMessages = computed(() => {
  return records.value.some(record => record.error_message);
});

// 计算是否显示 Postback URL 列（如果有任何记录有 postback_url）
const hasPostbackUrls = computed(() => {
  return records.value.some(record => record.postback_url);
});

// 监听对话框显示/隐藏
watch(visible, (val) => {
  if (val) {
    // 对话框打开时，重置分页并加载数据
    pagination.page = 1;
    handleSearch();
  }
});

// 监听 props 变化，重新加载数据
watch([() => props.conversionId, () => props.clientId, () => props.productId, () => props.publisherId], () => {
  if (visible.value) {
    // 如果对话框已打开，参数变化时重新加载数据
    pagination.page = 1;
    handleSearch();
  }
});
</script>

<style scoped>
.notification-records-content {
  padding: 20px;
}

.filter-bar {
  margin-bottom: 20px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>

