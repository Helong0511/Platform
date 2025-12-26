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
        <el-table-column prop="conversion_id" label="转化ID" width="100" />
        <el-table-column prop="notification_channel" label="渠道" width="100">
          <template #default="scope">
            <el-tag :type="getChannelTagType(scope.row.notification_channel)">
              {{ getChannelLabel(scope.row.notification_channel) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="notification_status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="getStatusTagType(scope.row.notification_status)">
              {{ getStatusLabel(scope.row.notification_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="notification_message" label="消息内容" min-width="200" show-overflow-tooltip />
        <el-table-column prop="error_message" label="错误信息" min-width="150" show-overflow-tooltip />
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
  clientId: { type: Number, default: null },
  productId: { type: Number, default: null }
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
    if (props.clientId) params.client_id = props.clientId;
    if (props.productId) params.product_id = props.productId;
    
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

const handleSizeChange = () => {
  loadRecords();
};

const handlePageChange = () => {
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
    sms: '短信'
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

watch(visible, (val) => {
  if (val) {
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

