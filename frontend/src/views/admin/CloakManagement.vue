<!--
  斗篷管理页面（CloakManagement.vue）

  功能区块：
  1. 工具栏：按斗篷名称搜索、分页列表
  2. 表格：可用性、像素、三阶段上报开关（载/点/转）、启用开关、操作按钮
  3. 编辑弹窗：新建/编辑斗篷配置（加载、点击、postback 三阶段 CAPI 参数）
  4. 上传弹窗：上传 {cloak_name}.html 桥页文件
  5. 测试弹窗：选择阶段 → 调用 test-report API → 展示主/备像素 CAPI 响应

  业务逻辑集中在 composable useCloakConfigs.js，本文件仅负责 UI 绑定。
-->
<template>
  <!-- 页面主模板 -->
  <div class="cloak-management">
    <!-- 页面标题与业务说明 -->
    <div class="page-header">
      <h2>斗篷管理</h2>
      <p>
        管理斗篷名称、像素与 Token；系统会检测磁盘是否存在对应 <code>{斗篷名}.html</code>，
        <strong>有则标识「可用」</strong>，无则<strong>不可用</strong>（不可开启，像素映射亦不生效）。可先保存配置再上传 HTML。
      </p>
    </div>

    <!-- 搜索与新增工具栏 -->
    <!-- 工具栏 -->
    <el-card shadow="never" class="toolbar-card">
      <!-- 表单区域 -->
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="斗篷名称">
          <el-input
            v-model="searchForm.cloak_name"
            placeholder="例如 master"
            clearable
            @keyup.enter="fetchConfigs"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
          <el-button type="success" :icon="Plus" @click="handleCreate">新增斗篷</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 斗篷配置列表：可用性由后端 bridge_html_present / is_usable 决定 -->
    <el-card shadow="never">
      <div class="table-wrapper">
      <!-- 数据表格 -->
      <el-table v-loading="loading" :data="tableData" border stripe>
        <el-table-column prop="cloak_name" label="斗篷名称" min-width="130" />
        <el-table-column label="可用性" width="128" align="center">
          <template #default="{ row }">
            <el-tooltip
              v-if="!rowIsUsable(row)"
              :content="`未检测到「${row.cloak_name}.html」，请先上传桥页文件`"
              placement="top"
            >
              <el-tag type="danger" size="small">不可用</el-tag>
            </el-tooltip>
            <el-tag v-else type="success" size="small">可用</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="pixel_id" label="像素ID" min-width="150" />
        <el-table-column label="Token" min-width="160">
          <template #default="{ row }">
            <span>{{ maskToken(row.access_token) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上报事件" min-width="220">
          <template #default="{ row }">
            <span>{{ reportEventCellLabel(row.report_event) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分阶段" width="168" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.load_report_enabled ? 'success' : 'info'">载</el-tag>
            <el-tag size="small" :type="row.click_report_enabled !== false ? 'success' : 'info'" style="margin-left: 4px"
              >点</el-tag
            >
            <el-tag size="small" :type="row.postback_report_enabled ? 'success' : 'info'" style="margin-left: 4px"
              >转</el-tag
            >
          </template>
        </el-table-column>
        <el-table-column label="金额/货币" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.report_event === 'Purchase'">
              {{ row.report_value != null ? row.report_value : '-' }} {{ row.report_currency || 'USD' }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="backup_pixel_id" label="备份像素ID" min-width="150">
          <template #default="{ row }">{{ row.backup_pixel_id || '-' }}</template>
        </el-table-column>
        <el-table-column label="备份Token" min-width="160">
          <template #default="{ row }">
            <span>{{ row.backup_access_token ? maskToken(row.backup_access_token) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开关" width="110" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_enabled"
              :disabled="!rowIsUsable(row) && !row.is_enabled"
              @change="(val) => handleToggle(row, val)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="380" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="handleEdit(row)">编辑</el-button>
            <el-button type="warning" link @click="handleOpenUpload(row)">上传HTML</el-button>
            <el-button type="success" link @click="handleTestReport(row)">测试上报</el-button>
            <el-button type="danger" link @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      </div>

      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
        />
      </div>
    </el-card>

    <!-- 新建/编辑弹窗：三阶段上报（载=load、点=click、转=postback） -->
    <!-- 弹窗 -->
    <el-dialog
      v-model="editDialogVisible"
      :title="editingId ? '编辑斗篷配置' : '新增斗篷配置'"
      width="900px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="formData" :rules="rules" label-width="150px">
        <el-form-item label="斗篷名称" prop="cloak_name">
          <el-input v-model="formData.cloak_name" placeholder="例如 master（对应 master.html）" />
        </el-form-item>
        <el-form-item label="像素ID" prop="pixel_id">
          <el-input v-model="formData.pixel_id" placeholder="例如 1124622134062236" />
        </el-form-item>
        <el-form-item label="Token" prop="access_token">
          <el-input v-model="formData.access_token" type="textarea" :rows="2" placeholder="例如 EAAif******iQZDZD" />
        </el-form-item>
        <el-form-item label="备份像素ID" prop="backup_pixel_id">
          <el-input v-model="formData.backup_pixel_id" placeholder="可不填，不填则不上报备份" />
        </el-form-item>
        <el-form-item label="备份Token" prop="backup_access_token">
          <el-input
            v-model="formData.backup_access_token"
            type="textarea"
            :rows="2"
            placeholder="可不填，不填则不上报备份"
          />
        </el-form-item>

        <el-divider content-position="left">1. 加载完成上报</el-divider>
        <el-form-item label="启用加载上报" prop="load_report_enabled">
          <el-switch v-model="formData.load_report_enabled" />
          <div class="switch-hint">开启后由服务端在桥页 HTML 中注入脚本，在 <code>DOMContentLoaded</code> 后请求 <code>/report?phase=load</code> 发 Facebook。</div>
        </el-form-item>
        <el-form-item label="加载上报事件" prop="load_report_event">
          <el-select
            v-model="formData.load_report_event"
            placeholder="选择或输入事件名"
            style="width: 100%"
            filterable
            allow-create
            default-first-option
          >
            <el-option v-for="opt in CLOAK_REPORT_EVENTS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="formData.load_report_event === 'Purchase'" label="加载金额" prop="load_report_value">
          <el-input-number
            v-model="formData.load_report_value"
            :min="0.01"
            :precision="2"
            :step="0.01"
            style="width: 100%"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item v-if="formData.load_report_event === 'Purchase'" label="加载货币" prop="load_report_currency">
          <el-input v-model="formData.load_report_currency" maxlength="10" placeholder="如 USD" />
        </el-form-item>

        <el-divider content-position="left">2. 点击跳转上报</el-divider>
        <el-form-item label="启用点击上报" prop="click_report_enabled">
          <el-switch v-model="formData.click_report_enabled" />
          <div class="switch-hint">关闭后仍统计点击与写入访问参数，但不向 Facebook 发送 CAPI。</div>
        </el-form-item>
        <el-form-item label="点击上报事件" prop="report_event">
          <el-select
            v-model="formData.report_event"
            placeholder="选择标准事件，或输入自定义（如 Click）"
            style="width: 100%"
            filterable
            allow-create
            default-first-option
          >
            <el-option
              v-for="opt in CLOAK_REPORT_EVENTS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <div class="switch-hint">
            与 Meta CAPI 的 event_name 一致；购物（Purchase）须填金额与货币。
          </div>
        </el-form-item>
        <el-form-item v-if="formData.report_event === 'Purchase'" label="点击金额" prop="report_value">
          <el-input-number
            v-model="formData.report_value"
            :min="0.01"
            :precision="2"
            :step="0.01"
            style="width: 100%"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item v-if="formData.report_event === 'Purchase'" label="点击货币" prop="report_currency">
          <el-input v-model="formData.report_currency" maxlength="10" placeholder="如 USD" />
        </el-form-item>

        <el-divider content-position="left">3. Postback 转化上报</el-divider>
        <el-form-item label="按斗篷配置转化上报" prop="postback_report_enabled">
          <el-switch v-model="formData.postback_report_enabled" />
          <div class="switch-hint">
            关闭时维持系统原逻辑：postback 成功且点击记录含 <code>fbclid</code> 时，按 <strong>payout</strong> 发
            <code>Purchase</code>。开启后：若点击 <code>url_params</code> 含 <code>dp=本斗篷名</code>（如
            <code>dp=145</code>），则按下方事件与金额（Purchase 金额可留空以使用 payout）发 CAPI。
          </div>
        </el-form-item>
        <el-form-item label="转化上报事件" prop="postback_report_event">
          <el-select
            v-model="formData.postback_report_event"
            placeholder="选择或输入事件名"
            style="width: 100%"
            filterable
            allow-create
            default-first-option
          >
            <el-option v-for="opt in CLOAK_REPORT_EVENTS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="formData.postback_report_event === 'Purchase'" label="转化固定金额" prop="postback_report_value">
          <el-input-number
            v-model="formData.postback_report_value"
            :min="0.01"
            :precision="2"
            :step="0.01"
            style="width: 100%"
            controls-position="right"
            clearable
          />
          <div class="switch-hint">留空则使用 postback 中的 payout 作为 Purchase 金额。</div>
        </el-form-item>
        <el-form-item v-if="formData.postback_report_event === 'Purchase'" label="转化货币" prop="postback_report_currency">
          <el-input v-model="formData.postback_report_currency" maxlength="10" placeholder="如 USD" />
        </el-form-item>

        <el-divider content-position="left">其它</el-divider>
        <el-form-item label="开关" prop="is_enabled">
          <div>
            <el-switch v-model="formData.is_enabled" />
            <div class="switch-hint">
              仅当已存在桥页文件 <code>{{ formData.cloak_name || '斗篷名称' }}.html</code> 时可开启；新建请先<strong>关闭开关</strong>保存，再上传 HTML 后开启。
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 桥页 HTML 上传：保存为 {cloak_name}.html，上传后可用性变为「可用」 -->
    <el-dialog
      v-model="uploadDialogVisible"
      title="上传桥页 HTML"
      width="520px"
      :close-on-click-modal="false"
      destroy-on-close
      @closed="handleUploadDialogClosed"
    >
      <el-alert type="info" :closable="false" style="margin-bottom: 12px;">
        将保存为磁盘文件 <strong>{{ uploadTargetRow?.cloak_name || '-' }}.html</strong>（与短链
        <code>?dp=斗篷名称</code> 对应）。若已存在则会覆盖。
      </el-alert>
      <p style="margin: 0 0 8px; color: #909399; font-size: 13px;">
        要求 UTF-8 编码，内容需包含 <code>&lt;!DOCTYPE html&gt;</code> 或 <code>&lt;html</code>，单文件不超过 2MB。
      </p>
      <el-upload
        :key="uploadDialogKey"
        drag
        :limit="1"
        accept=".html,text/html"
        :auto-upload="false"
        :on-change="handleHtmlFileChange"
        :on-exceed="handleHtmlExceed"
      >
        <el-icon class="el-icon--upload"><Upload /></el-icon>
        <div class="el-upload__text">拖拽文件到此处，或 <em>点击选择</em></div>
        <template #tip>
          <div class="el-upload__tip">仅 .html；上传成功后列表「可用性」将变为可用</div>
        </template>
      </el-upload>
      <template #footer>
        <el-button @click="uploadDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitBridgeHtml">上传</el-button>
      </template>
    </el-dialog>

    <!-- 测试上报：先选择阶段（载/点/转），再向 Facebook CAPI 发送模拟事件 -->
    <el-dialog
      v-model="testPhaseDialogVisible"
      title="选择测试上报类型"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-alert type="info" :closable="false" style="margin-bottom: 12px;">
        斗篷：{{ testPhaseTargetRow?.cloak_name || '-' }}。请选择要模拟的上报阶段，将按该阶段在编辑中的事件与金额向 Facebook 发送测试 CAPI。
      </el-alert>
      <el-radio-group v-model="testPhase" style="display: flex; flex-direction: column; gap: 12px;">
        <el-radio v-for="opt in CLOAK_TEST_REPORT_PHASES" :key="opt.value" :label="opt.value">
          {{ opt.label }}
        </el-radio>
      </el-radio-group>
      <template #footer>
        <el-button @click="testPhaseDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="testSubmitting" @click="submitTestReport">开始测试</el-button>
      </template>
    </el-dialog>

    <!-- 测试上报结果：展示主像素与备份像素的请求/响应详情（Token 已脱敏） -->
    <el-dialog
      v-model="testDialogVisible"
      title="测试上报结果"
      width="900px"
      :close-on-click-modal="false"
    >
      <el-alert type="info" :closable="false" style="margin-bottom: 12px;">
        当前斗篷：{{ currentTestingRow?.cloak_name || '-' }}；上报阶段：{{ currentTestPhaseLabel }}；上报事件：{{
          currentTestEventMeta.event
        }}
        <template v-if="currentTestEventMeta.event === 'Purchase'">
          ；金额：{{ currentTestEventMeta.value ?? '（测试默认）' }}
          {{ currentTestEventMeta.currency || 'USD' }}
        </template>
      </el-alert>
      <el-descriptions title="主上报结果" :column="1" border>
        <el-descriptions-item label="请求地址">{{ testResult?.primary?.request_url || '-' }}</el-descriptions-item>
        <el-descriptions-item label="请求参数">
          <pre class="json-pre">{{ formatJson(testResult?.primary?.request_query) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="请求体">
          <pre class="json-pre">{{ formatJson(testResult?.primary?.request_body) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="返回状态码">{{ testResult?.primary?.response_status ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="返回信息">
          <pre class="json-pre">{{ formatJson(testResult?.primary?.response_body) }}</pre>
        </el-descriptions-item>
      </el-descriptions>

      <el-descriptions v-if="testResult?.backup" title="备份上报结果" :column="1" border style="margin-top: 16px;">
        <el-descriptions-item label="请求地址">{{ testResult.backup.request_url || '-' }}</el-descriptions-item>
        <el-descriptions-item label="请求参数">
          <pre class="json-pre">{{ formatJson(testResult.backup.request_query) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="请求体">
          <pre class="json-pre">{{ formatJson(testResult.backup.request_body) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="返回状态码">{{ testResult.backup.response_status ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="返回信息">
          <pre class="json-pre">{{ formatJson(testResult.backup.response_body) }}</pre>
        </el-descriptions-item>
      </el-descriptions>
      <el-alert v-else type="warning" :closable="false" style="margin-top: 16px;">
        未配置备份像素ID/备份Token，本次已跳过备份上报。
      </el-alert>
      <template #footer>
        <el-button type="primary" @click="testDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 斗篷管理页面：列表、编辑三阶段上报、上传桥页 HTML、测试 CAPI。
 * 业务状态与 API 调用集中在 composable useCloakConfigs.js。
 */
import { Plus, Refresh, Search, Upload } from '@element-plus/icons-vue';
import { useCloakConfigs } from '../../composables/useCloakConfigs';

const {
  CLOAK_REPORT_EVENTS,
  CLOAK_TEST_REPORT_PHASES,
  loading,
  saving,
  tableData,
  formRef,
  editDialogVisible,
  testDialogVisible,
  testPhaseDialogVisible,
  testPhase,
  testPhaseTargetRow,
  testSubmitting,
  currentTestPhaseLabel,
  currentTestEventMeta,
  uploadDialogVisible,
  uploadDialogKey,
  uploadTargetRow,
  uploadSelectedFile,
  uploading,
  editingId,
  currentTestingRow,
  testResult,
  searchForm,
  pagination,
  formData,
  rules,
  rowIsUsable,
  maskToken,
  formatJson,
  reportEventCellLabel,
  fetchConfigs,
  handleSearch,
  handleReset,
  handleCreate,
  handleEdit,
  handleSave,
  handleDelete,
  handleToggle,
  handleOpenUpload,
  handleHtmlFileChange,
  handleHtmlExceed,
  handleUploadDialogClosed,
  submitBridgeHtml,
  handleTestReport,
  submitTestReport,
} = useCloakConfigs();
</script>

<style scoped>
.cloak-management {
  padding: 20px;
}

.page-header {
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0;
}

.page-header p {
  margin: 8px 0 0;
  color: #909399;
}

.toolbar-card {
  margin-bottom: 16px;
}

.pagination {
  margin-top: 16px;
  text-align: right;
}

.table-wrapper {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

@media (max-width: 767px) {
  .table-wrapper :deep(.el-table) {
    min-width: 960px;
  }

  .pagination {
    text-align: center;
  }
}

.switch-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.switch-hint code {
  font-size: 12px;
}

.json-pre {
  margin: 0;
  max-height: 220px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  background: #f5f7fa;
  padding: 10px;
  border-radius: 4px;
}
</style>
