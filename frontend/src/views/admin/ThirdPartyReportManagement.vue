<!--
  管理端 - 第三方报表
  @file views/admin/ThirdPartyReportManagement.vue
-->
<template>
  <!-- 页面主模板 -->
  <div class="third-party-report-management-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1>第三方上报日志</h1>
        <div class="stats-info" v-if="stats">
          <span class="stat-item">
            <span class="stat-label">总上报数：</span>
            <span class="stat-value">{{ stats.total || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">成功：</span>
            <span class="stat-value success">{{ stats.success || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">失败：</span>
            <span class="stat-value danger">{{ stats.failed || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">处理中：</span>
            <span class="stat-value warning">{{ stats.pending || 0 }}</span>
          </span>
        </div>
      </div>
    </div>

    <!-- 筛选控件 -->
    <!-- 筛选区 -->
    <el-card class="filter-card" shadow="never">
      <!-- 表单区域 -->
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="来源">
          <el-select v-model="searchForm.source" placeholder="全部" clearable style="width: 150px;" name="source"
            popper-class="select-dropdown" :teleported="true">
            <el-option label="全部" value=""></el-option>
            <el-option label="短链接" value="short_link"></el-option>
            <el-option label="Postback" value="postback"></el-option>
            <el-option label="其他" value="unknown"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="广告ID">
          <el-input v-model="searchForm.adsid" placeholder="输入广告ID搜索" clearable @keyup.enter="fetchLogs"
            style="width: 250px;" name="adsid">
            <template #prefix>
              <el-icon :size="16">
                <Search />
              </el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="事件类型">
          <el-select v-model="searchForm.event" placeholder="全部" clearable style="width: 150px;" name="event"
            popper-class="select-dropdown" :teleported="true">
            <el-option label="全部" value=""></el-option>
            <el-option label="ViewContent" value="ViewContent"></el-option>
            <el-option label="Purchase" value="Purchase"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部" clearable style="width: 120px;" name="status"
            popper-class="select-dropdown" :teleported="true">
            <el-option label="全部" value=""></el-option>
            <el-option label="成功" value="success"></el-option>
            <el-option label="失败" value="failed"></el-option>
            <el-option label="处理中" value="pending"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围" class="date-range-item">
          <el-date-picker v-model="dateRange" name="dateRange" type="datetimerange" range-separator="至"
            start-placeholder="开始时间" end-placeholder="结束时间" format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss" style="width: 400px;" class="date-picker-full" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchLogs" :loading="loading" :icon="Search">
            查询
          </el-button>
          <el-button @click="resetFilter" :icon="Refresh">
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 日志数据表格 -->
    <el-card class="data-table-card" shadow="never">
      <!-- 卡片标题栏 -->
    <template #header>
        <div class="table-header">
          <span>上报日志列表</span>
          <el-button type="link" :icon="Setting" @click="columnSettingVisible = true" style="float: right;">
            列设置
          </el-button>
        </div>
      </template>
      <el-table v-loading="loading" :data="logs" border stripe style="width: 100%">
        <el-table-column v-if="columnVisibility.id" prop="id" label="ID" width="80" align="center" />
        <el-table-column v-if="columnVisibility.source" prop="source" label="来源" width="120" align="center">
          <template #default="scope">
            <el-tag :type="getSourceTag(scope.row.source)" size="small">
              {{ getSourceLabel(scope.row.source) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.adsid" prop="adsid" label="广告ID" min-width="180"
          show-overflow-tooltip />
        <el-table-column v-if="columnVisibility.event" prop="event" label="事件类型" width="120" align="center">
          <template #default="scope">
            <el-tag size="small">{{ scope.row.event }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.conversion_id" prop="conversion_id" label="转化ID" min-width="180"
          show-overflow-tooltip>
          <template #default="scope">
            <el-button v-if="scope.row.conversion_id" type="primary" link size="small"
              @click="handleConversionIdClick(scope.row.conversion_id)">
              {{ scope.row.conversion_id }}
            </el-button>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.currency" prop="currency" label="货币类型" width="100" align="center">
          <template #default="scope">
            {{ scope.row.currency || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.amount" prop="amount" label="支付金额" width="120" align="center">
          <template #default="scope">
            {{ scope.row.amount || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.status" prop="status" label="状态" width="90" align="center">
          <template #default="scope">
            <el-tag :type="getStatusTag(scope.row.status)" size="small">
              {{ getStatusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.attempt_count" prop="attempt_count" label="尝试次数" width="100"
          align="center" />
        <el-table-column v-if="columnVisibility.response_status" prop="response_status" label="响应状态码" width="120"
          align="center">
          <template #default="scope">
            <el-tag v-if="scope.row.response_status" :type="getResponseStatusTag(scope.row.response_status)"
              size="small">
              {{ scope.row.response_status }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.log_id" prop="log_id" label="日志ID" min-width="150"
          show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.log_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.use_hash" prop="use_hash" label="哈希处理" width="120" align="center">
          <template #default="scope">
            <el-button size="small" :type="scope.row.use_hash ? 'success' : 'danger'"
              @click="handleHashToggle(scope.row)" :loading="scope.row._hashLoading"
              :disabled="scope.row._hashLoading || loading">
              {{ scope.row.use_hash ? '启用' : '禁用' }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.created_at" prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDateTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.report_success_time" prop="report_success_time" label="成功时间"
          width="180">
          <template #default="scope">
            {{ scope.row.report_success_time ? formatDateTime(scope.row.report_success_time) : '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.report_params" prop="report_params_preview" label="完整上报参数" min-width="200"
          show-overflow-tooltip>
          <template #default="scope">
            <span v-if="scope.row.report_params_preview" class="report-params-preview">
              {{ scope.row.report_params_preview }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="scope">
            <el-button type="primary" link size="small" @click="handleViewDetail(scope.row)">
              详情
            </el-button>
            <el-button type="warning" link size="small" @click="handleEdit(scope.row)">
              编辑
            </el-button>
            <el-button v-if="scope.row.status === 'failed'" type="danger" link size="small"
              @click="handleRetry(scope.row)">
              重新上报
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!loading && logs.length === 0"
        description="暂无上报日志，可调整筛选条件或扩大时间范围后重试"
        style="margin: 24px 0;"
      />

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]" :total="pagination.total"
          :layout="isMobile ? 'total, prev, pager, next' : 'total, sizes, prev, pager, next, jumper'" />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog v-model="detailDialogVisible" title="上报日志详情" :width="isMobile ? '95%' : '1000px'"
      class="report-detail-dialog" :close-on-click-modal="false" :append-to-body="true">
      <div v-if="currentLog" class="report-detail-content">
        <el-descriptions :column="isMobile ? 1 : 2" border>
          <el-descriptions-item label="日志ID">{{ currentLog.id }}</el-descriptions-item>
          <el-descriptions-item label="来源">
            <el-tag :type="getSourceTag(currentLog.source)">
              {{ getSourceLabel(currentLog.source) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="广告ID">{{ currentLog.adsid }}</el-descriptions-item>
          <el-descriptions-item label="事件类型">
            <el-tag size="small">{{ currentLog.event }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="转化ID">{{ currentLog.conversion_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="货币类型">{{ currentLog.currency || '-' }}</el-descriptions-item>
          <el-descriptions-item label="支付金额">{{ currentLog.amount || '-' }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusTag(currentLog.status)">
              {{ getStatusLabel(currentLog.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="尝试次数">{{ currentLog.attempt_count }} / {{ currentLog.max_attempts
          }}</el-descriptions-item>
          <el-descriptions-item label="邮箱（已脱敏）">
            {{ currentLog.email || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="IP地址（已脱敏）">
            {{ currentLog.ip || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="手机号（已脱敏）">
            {{ currentLog.phone || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="哈希处理">
            <el-tag :type="currentLog.use_hash ? 'success' : 'danger'">
              {{ currentLog.use_hash ? '启用' : '禁用' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="响应状态码">
            <el-tag v-if="currentLog.response_status" :type="getResponseStatusTag(currentLog.response_status)"
              size="small">
              {{ currentLog.response_status }}
            </el-tag>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="日志ID">{{ currentLog.log_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(currentLog.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="上报开始时间">
            {{ currentLog.report_start_time ? formatDateTime(currentLog.report_start_time) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="上报成功时间">
            {{ currentLog.report_success_time ? formatDateTime(currentLog.report_success_time) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="完成时间">
            {{ currentLog.completed_at ? formatDateTime(currentLog.completed_at) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="用户代理（已隐藏）" :span="2">
            {{ currentLog.ua || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="完整上报参数" :span="2" v-if="currentLog.report_params">
            <pre class="json-content">{{ formatJson(currentLog.report_params) }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="响应内容" :span="2" v-if="currentLog.response_body">
            <pre class="json-content">{{ formatJson(currentLog.response_body) }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="错误信息" :span="2" v-if="currentLog.error_message">
            <el-alert type="error" :closable="false">
              {{ currentLog.error_message }}
            </el-alert>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <div v-else class="loading-placeholder">
        <el-icon class="is-loading">
          <Loading />
        </el-icon>
        <span>加载中...</span>
      </div>
      <template #footer>
        <el-button type="primary" @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑上报参数" :width="isMobile ? '95%' : '600px'" class="edit-dialog"
      :close-on-click-modal="false" :append-to-body="true">
      <el-form :model="editForm" label-width="120px">
        <el-form-item label="广告ID">
          <el-input v-model="editForm.adsid" placeholder="请输入广告ID" />
        </el-form-item>
        <el-form-item label="事件类型">
          <el-select v-model="editForm.event" placeholder="请选择事件类型" style="width: 100%;">
            <el-option label="ViewContent" value="ViewContent" />
            <el-option label="Purchase" value="Purchase" />
          </el-select>
        </el-form-item>
        <el-form-item label="转化ID">
          <el-input v-model="editForm.conversion_id" placeholder="请输入转化ID" />
        </el-form-item>
        <el-form-item label="货币类型">
          <el-input v-model="editForm.currency" placeholder="请输入货币类型（如USD）" />
        </el-form-item>
        <el-form-item label="支付金额">
          <el-input v-model.number="editForm.amount" type="number" placeholder="请输入支付金额" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="editForm.email" placeholder="留空保持原值；输入新邮箱以替换" />
        </el-form-item>
        <el-form-item label="IP地址">
          <el-input v-model="editForm.ip" placeholder="留空保持原值；输入新 IP 以替换" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="editForm.phone" placeholder="留空保持原值；输入新手机号以替换" />
        </el-form-item>
        <el-form-item label="用户代理">
          <el-input v-model="editForm.ua" type="textarea" :rows="3" placeholder="留空保持原值；输入新 UA 以替换" />
        </el-form-item>
        <el-form-item label="完整上报参数">
          <el-input v-model="editForm.report_params" type="textarea" :rows="4" placeholder="留空保持原值；输入新的 JSON 参数以替换" />
        </el-form-item>
        <el-form-item label="哈希处理">
          <el-switch v-model="editForm.use_hash" />
          <span style="margin-left: 10px; color: var(--text-secondary);">
            开启后会对 email、ip、phone 进行 SHA256 哈希处理
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 列设置对话框 -->
    <el-dialog v-model="columnSettingVisible" title="列显示设置" width="500px" @close="saveColumnVisibility">
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="id" :disabled="true">ID（固定显示）</el-checkbox>
        <el-checkbox label="source">来源</el-checkbox>
        <el-checkbox label="adsid">广告ID</el-checkbox>
        <el-checkbox label="event">事件类型</el-checkbox>
        <el-checkbox label="conversion_id">转化ID</el-checkbox>
        <el-checkbox label="currency">货币类型</el-checkbox>
        <el-checkbox label="amount">支付金额</el-checkbox>
        <el-checkbox label="status">状态</el-checkbox>
        <el-checkbox label="attempt_count">尝试次数</el-checkbox>
        <el-checkbox label="response_status">响应状态码</el-checkbox>
        <el-checkbox label="log_id">日志ID</el-checkbox>
        <el-checkbox label="use_hash">哈希处理</el-checkbox>
        <el-checkbox label="report_params">完整上报参数</el-checkbox>
        <el-checkbox label="created_at" :disabled="true">创建时间（固定显示）</el-checkbox>
        <el-checkbox label="report_success_time">成功时间</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import {
  ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem,
  ElInput, ElSelect, ElOption, ElTag, ElDialog, ElIcon, ElMessage, ElMessageBox,
  ElDescriptions, ElDescriptionsItem, ElDatePicker, ElAlert, ElCheckboxGroup, ElCheckbox,
  ElSwitch
} from 'element-plus';
import { Search, Refresh, Loading, Setting } from '@element-plus/icons-vue';
import { useAuthStore } from '../../store';
import { getThirdPartyReport, updateThirdPartyReport, retryThirdPartyReport } from '../../api/third-party-report';
import { formatDateTime } from '../../utils/dateFormat';
import { useDevice } from '../../composables/useDevice';
import { useThirdPartyReportColumnVisibility } from '../../composables/useThirdPartyReportColumnVisibility';
import { useThirdPartyReports } from '../../composables/useThirdPartyReports';
import {
  formatReportJson,
  getCurrentMonthRange,
  getResponseStatusTag,
  getSourceLabel,
  getSourceTag,
  getStatusLabel,
  getStatusTag,
} from '../../utils/thirdPartyReportFormat';
import { logger } from '../../utils/logger';

const router = useRouter();
const authStore = useAuthStore();

const { isMobile } = useDevice();

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility,
} = useThirdPartyReportColumnVisibility();

const isInitializing = ref(true);
const {
  logs,
  loading,
  stats,
  pagination,
  searchForm,
  dateRange,
  fetchLogs,
  resetFilter,
  bindPaginationWatch,
} = useThirdPartyReports(authStore, router);

bindPaginationWatch(isInitializing);

// 详情对话框
const detailDialogVisible = ref(false);
const currentLog = ref(null);

// 编辑对话框
const editDialogVisible = ref(false);
const editLogId = ref(null);
const editForm = reactive({
  adsid: '',
  event: '',
  conversion_id: '',
  currency: '',
  amount: '',
  email: '',
  ip: '',
  phone: '',
  ua: '',
  report_params: '',
  use_hash: true
});

const formatJson = formatReportJson;

// 查看详情
const handleViewDetail = async (log) => {
  try {
    const data = await getThirdPartyReport(log.id);
    currentLog.value = data;
    detailDialogVisible.value = true;
  } catch (error) {
    logger.error('加载上报详情失败:', error);
  }
};

// 编辑日志
const handleEdit = async (log) => {
  try {
    const detail = await getThirdPartyReport(log.id);
    editLogId.value = detail.id;
    editForm.adsid = detail.adsid || '';
    editForm.event = detail.event || '';
    editForm.conversion_id = detail.conversion_id || '';
    editForm.currency = detail.currency || '';
    editForm.amount = detail.amount || '';
    editForm.email = ''; // 详情接口只返回脱敏值，留空表示不修改原始字段。
    editForm.ip = ''; // 详情接口只返回脱敏值，留空表示不修改原始字段。
    editForm.phone = ''; // 详情接口只返回脱敏值，留空表示不修改原始字段。
    editForm.ua = ''; // 详情接口只返回脱敏值，留空表示不修改原始字段。
    editForm.report_params = ''; // 详情接口只返回脱敏值，留空表示不修改原始字段。
    editForm.use_hash = detail.use_hash !== false;
    editDialogVisible.value = true;
  } catch (error) {
    ElMessage.error('加载日志详情失败，请重试');
  }
};

// 保存编辑
const handleSaveEdit = async () => {
  try {
    const params = {};
    if (editForm.adsid) params.adsid = editForm.adsid;
    if (editForm.event) params.event = editForm.event;
    if (editForm.conversion_id) params.conversion_id = editForm.conversion_id;
    if (editForm.currency) params.currency = editForm.currency;
    if (editForm.amount !== '' && editForm.amount !== null && editForm.amount !== undefined) params.amount = editForm.amount;
    if (editForm.email) params.email = editForm.email;
    if (editForm.ip) params.ip = editForm.ip;
    if (editForm.phone) params.phone = editForm.phone;
    if (editForm.ua) params.ua = editForm.ua;
    if (editForm.report_params) params.report_params = editForm.report_params;
    params.use_hash = editForm.use_hash;

    await updateThirdPartyReport(editLogId.value, params);
    ElMessage.success('更新成功');
    editDialogVisible.value = false;
    fetchLogs();
  } catch (error) {
    ElMessage.error('更新失败');
  }
};

// 重新上报
const handleRetry = async (log) => {
  try {
    await ElMessageBox.confirm(
      '确定要重新上报这条日志吗？',
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    await retryThirdPartyReport(log.id);
    ElMessage.success('已触发重新上报，请稍后刷新查看结果');
    fetchLogs();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('重新上报失败');
    }
  }
};

// 切换哈希处理状态
const handleHashToggle = async (log) => {
  try {
    // 保存旧值
    const oldValue = log.use_hash;
    // 立即更新UI
    log.use_hash = !oldValue;
    // 设置加载状态
    log._hashLoading = true;

    // 调用API更新状态
    await updateThirdPartyReport(log.id, { use_hash: log.use_hash });

    ElMessage.success(`哈希处理已${log.use_hash ? '启用' : '禁用'}`);
    // 刷新日志列表
    fetchLogs();
  } catch (error) {
    // 恢复原值
    log.use_hash = !log.use_hash;
    ElMessage.error('切换哈希处理状态失败');
  } finally {
    // 清除加载状态
    log._hashLoading = false;
  }
};

// 点击转化ID，在新窗口打开短链接访问记录页面并搜索
const handleConversionIdClick = async (conversionId) => {
  if (!conversionId) return
  try {
    // 构建URL
    const url = new URL(window.location.origin + '/app/admin/click-log')
    url.searchParams.append('conversion_id', conversionId)
    // 在新窗口中打开
    window.open(url.toString(), '_blank')
  } catch (error) {
    logger.error('打开短链接访问记录页面失败:', error)
    ElMessage.error('打开失败，请重试')
  }
};

// 初始化
onMounted(async () => {
  loadColumnVisibility()
  await nextTick();

  setTimeout(async () => {
    try {
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => {
          reject(new Error('页面加载超时，请检查网络连接或刷新页面'));
        }, 20000);
      });

      await Promise.race([
        fetchLogs(),
        timeoutPromise
      ]);
    } catch (error) {
      if (error.message && error.message.includes('超时')) {
        ElMessage.error(error.message);
        loading.value = false;
      } else {
        loading.value = false;
      }
    } finally {
      await nextTick();
      isInitializing.value = false;
    }
  }, 0);
});
</script>

<style scoped>
.third-party-report-management-container {
  width: 100%;
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-xl);
  padding: var(--spacing-xl);
  background-color: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
  flex-wrap: wrap;
  gap: var(--spacing-md);
}

.page-header h1 {
  margin: 0 0 var(--spacing-md) 0;
  font-size: var(--font-size-title);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.stats-info {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-lg);
  padding: var(--spacing-sm) 0;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-base);
}

.stat-label {
  color: var(--text-secondary);
}

.stat-value {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.stat-value.success {
  color: var(--success-color);
}

.stat-value.danger {
  color: var(--danger-color);
}

.stat-value.warning {
  color: var(--warning-color);
}

.filter-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.data-table-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
  overflow: hidden;
}

.data-table-card :deep(.el-card__body) {
  padding: var(--spacing-xl);
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-lg);
  color: var(--text-primary);
}

.pagination-container {
  margin-top: var(--spacing-lg);
  padding: var(--spacing-lg) 0;
  text-align: right;
  border-top: 1px solid var(--border-lighter);
}

@media (max-width: 767px) {
  .third-party-report-management-container {
    padding: var(--spacing-md);
  }

  .page-header {
    padding: var(--spacing-md);
    margin-bottom: var(--spacing-md);
  }

  .page-header h1 {
    font-size: var(--font-size-xl);
    margin-bottom: var(--spacing-sm);
  }

  .stats-info {
    flex-direction: column;
    gap: var(--spacing-sm);
    margin-top: var(--spacing-sm);
  }

  .stat-item {
    font-size: var(--font-size-sm);
  }

  .filter-card {
    margin-bottom: var(--spacing-md);
    overflow: visible;
  }

  .filter-card :deep(.el-card__body) {
    padding: var(--spacing-md);
    overflow: visible;
    max-height: none;
  }

  .data-table-card {
    margin-bottom: var(--spacing-md);
  }

  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .el-table {
    font-size: var(--font-size-sm);
    min-width: 1000px;
  }

  .el-table :deep(.el-table__cell) {
    padding: var(--spacing-xs) var(--spacing-sm);
    word-break: break-word;
  }

  .el-table :deep(.el-table__header th),
  .el-table :deep(.el-table__body td) {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs);
  }

  .pagination-container {
    margin-top: var(--spacing-md);
    justify-content: center;
  }
}

.filter-form {
  margin: 0;
}

.report-detail-dialog :deep(.el-dialog__body) {
  padding: var(--spacing-xl);
  max-height: calc(100vh - 200px);
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  position: relative;
}

.report-detail-dialog :deep(.el-dialog) {
  overflow: visible !important;
}

.report-detail-content {
  width: 100%;
  overflow: visible;
}

.report-detail-content :deep(.el-descriptions) {
  width: 100%;
}

.report-detail-content :deep(.el-descriptions__table) {
  width: 100%;
  table-layout: auto;
}

.report-detail-content :deep(.el-descriptions__label),
.report-detail-content :deep(.el-descriptions-item__label) {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  min-width: 120px;
}

.report-detail-content :deep(.el-descriptions__content),
.report-detail-content :deep(.el-descriptions-item__content) {
  color: var(--text-regular);
  word-break: break-word;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.loading-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xxxxl);
  gap: var(--spacing-md);
  color: var(--text-secondary);
}

.loading-placeholder .is-loading {
  animation: rotating 2s linear infinite;
  font-size: var(--font-size-xl);
}

@keyframes rotating {
  0% {
    transform: rotate(0deg);
  }

  100% {
    transform: rotate(360deg);
  }
}

.json-content {
  background: var(--bg-secondary);
  padding: var(--spacing-md);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  max-height: 400px;
  overflow: auto;
  margin: 0;
  word-break: break-word;
  word-wrap: break-word;
  overflow-wrap: break-word;
  white-space: pre-wrap;
  color: var(--text-primary);
  line-height: var(--line-height-loose);
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
}

@media (max-width: 767px) {
  .filter-form {
    display: flex !important;
    flex-direction: column !important;
  }

  .filter-form :deep(.el-form--inline) {
    display: flex !important;
    flex-direction: column !important;
  }

  .filter-form :deep(.el-form-item) {
    width: 100% !important;
    margin-right: 0 !important;
    margin-bottom: var(--spacing-md) !important;
    display: flex !important;
    flex-direction: column !important;
  }

  .filter-form :deep(.el-form-item__label) {
    width: 100% !important;
    text-align: left !important;
    margin-bottom: var(--spacing-xs) !important;
    padding: 0 !important;
    margin-right: 0 !important;
    float: none !important;
    justify-content: flex-start !important;
    align-items: flex-start !important;
    display: block !important;
  }

  .filter-form :deep(.el-form-item__content) {
    width: 100% !important;
    margin-left: 0 !important;
    flex: 1 !important;
  }

  .filter-form :deep(.el-input),
  .filter-form :deep(.el-select),
  .filter-form :deep(.el-date-editor),
  .filter-form :deep(.el-date-picker) {
    width: 100% !important;
    max-width: 100% !important;
  }

  .filter-form :deep(.el-input__wrapper) {
    min-height: var(--touch-target-size);
    width: 100% !important;
  }

  .filter-form :deep(.el-select .el-input__wrapper) {
    min-height: var(--touch-target-size);
    width: 100% !important;
  }

  .filter-form :deep(.el-date-editor.el-input__wrapper) {
    width: 100% !important;
    min-height: var(--touch-target-size);
  }

  .date-range-item :deep(.el-form-item__content) {
    width: 100% !important;
  }

  .date-picker-full {
    width: 100% !important;
    max-width: 100% !important;
  }

  .date-picker-full :deep(.el-input__wrapper) {
    width: 100% !important;
  }

  .date-picker-full :deep(.el-range-separator) {
    width: auto !important;
    padding: 0 var(--spacing-xs);
  }

  .date-picker-full :deep(.el-range-input) {
    width: calc(50% - 20px) !important;
    flex: 1 !important;
  }

  .filter-form :deep(.el-form-item:last-child) {
    display: flex !important;
    flex-direction: row !important;
    gap: var(--spacing-sm);
    margin-top: var(--spacing-sm);
    margin-bottom: 0 !important;
    width: 100% !important;
  }

  .filter-form :deep(.el-form-item:last-child .el-form-item__label) {
    display: none !important;
  }

  .filter-form :deep(.el-form-item:last-child .el-form-item__content) {
    width: 100% !important;
    display: flex !important;
    flex-direction: row !important;
    gap: var(--spacing-sm);
    margin-left: 0 !important;
  }

  .filter-form :deep(.el-form-item:last-child .el-button) {
    flex: 1;
    min-height: var(--touch-target-size);
    width: auto;
    white-space: nowrap;
  }

  .filter-form :deep(.el-form-item:last-child .el-button .el-icon) {
    margin-right: var(--spacing-xs);
  }

  .el-table :deep(.el-button--link) {
    min-height: var(--touch-target-size);
    padding: var(--spacing-xs) var(--spacing-sm);
  }
}
</style>
