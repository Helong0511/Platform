<template>
  <div class="cloak-management">
    <div class="page-header">
      <h2>斗篷管理</h2>
      <p>
        管理斗篷名称、像素与 Token；系统会检测磁盘是否存在对应 <code>{斗篷名}.html</code>，
        <strong>有则标识「可用」</strong>，无则<strong>不可用</strong>（不可开启，像素映射亦不生效）。可先保存配置再上传 HTML。
      </p>
    </div>

    <el-card shadow="never" class="toolbar-card">
      <el-form :inline="true" :model="searchForm">
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

    <el-card shadow="never">
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

    <el-dialog
      v-model="testDialogVisible"
      title="测试上报结果"
      width="900px"
      :close-on-click-modal="false"
    >
      <el-alert type="info" :closable="false" style="margin-bottom: 12px;">
        当前斗篷：{{ currentTestingRow?.cloak_name || '-' }}；上报事件：{{
          currentTestingRow?.report_event || 'ViewContent'
        }}
        <template v-if="currentTestingRow?.report_event === 'Purchase'">
          ；金额：{{ currentTestingRow?.report_value }} {{ currentTestingRow?.report_currency || 'USD' }}
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
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Plus, Refresh, Search, Upload } from '@element-plus/icons-vue';
import {
  createCloakConfig,
  deleteCloakConfig,
  getCloakConfigs,
  testCloakReport,
  updateCloakConfig,
  uploadCloakBridgeHtml
} from '../../api/cloak-config';

/**
 * Meta 官方标准事件 + 中文说明；须与后端 app/schemas/cloak.py 中 FACEBOOK_STANDARD_EVENT_NAMES 一致。
 * 另支持自定义 event_name（如 Click）：见 validateReportEventName 与后端 validate_cloak_report_event_name。
 */
const CLOAK_REPORT_EVENTS = [
  { value: 'PageView', label: 'PageView（页面浏览）' },
  { value: 'ViewContent', label: 'ViewContent（查看内容）' },
  { value: 'Search', label: 'Search（搜索）' },
  { value: 'AddToCart', label: 'AddToCart（加入购物车）' },
  { value: 'AddToWishlist', label: 'AddToWishlist（加入心愿单）' },
  { value: 'AddPaymentInfo', label: 'AddPaymentInfo（填写支付信息）' },
  { value: 'InitiateCheckout', label: 'InitiateCheckout（发起结账）' },
  { value: 'Purchase', label: 'Purchase（购买）' },
  { value: 'Lead', label: 'Lead（潜在客户）' },
  { value: 'CompleteRegistration', label: 'CompleteRegistration（完成注册）' },
  { value: 'Contact', label: 'Contact（发起联系）' },
  { value: 'Subscribe', label: 'Subscribe（订阅）' },
  { value: 'StartTrial', label: 'StartTrial（开始试用）' },
  { value: 'SubmitApplication', label: 'SubmitApplication（提交申请）' },
  { value: 'Schedule', label: 'Schedule（预约）' },
  { value: 'FindLocation', label: 'FindLocation（查找位置）' },
  { value: 'Donate', label: 'Donate（捐赠）' },
  { value: 'CustomizeProduct', label: 'CustomizeProduct（定制商品）' }
];

const FACEBOOK_STANDARD_EVENT_SET = new Set(CLOAK_REPORT_EVENTS.map((o) => o.value));

/** 与后端 _CLOAK_REPORT_EVENT_CUSTOM_RE 一致：自定义事件（如 Click） */
const CLOAK_CUSTOM_REPORT_EVENT_RE = /^[A-Za-z][A-Za-z0-9_]{1,62}$/;

function validateReportEventName(_rule, value, callback) {
  const v = (value || '').trim();
  if (!v) {
    callback(new Error('请选择或输入上报事件'));
    return;
  }
  if (FACEBOOK_STANDARD_EVENT_SET.has(v) || CLOAK_CUSTOM_REPORT_EVENT_RE.test(v)) {
    callback();
    return;
  }
  callback(new Error('须为 Meta 标准事件名，或字母开头的自定义名（仅字母、数字、下划线，2～64 字符）'));
}

function reportEventCellLabel(code) {
  const raw = (code || '').trim();
  if (!raw) return '-';
  const hit = CLOAK_REPORT_EVENTS.find((o) => o.value === raw);
  if (hit) return hit.label;
  return `${raw}（自定义）`;
}

const loading = ref(false);
const saving = ref(false);
const tableData = ref([]);
const formRef = ref(null);
const editDialogVisible = ref(false);
const testDialogVisible = ref(false);
const uploadDialogVisible = ref(false);
const uploadDialogKey = ref(0);
const uploadTargetRow = ref(null);
const uploadSelectedFile = ref(null);
const uploading = ref(false);
const editingId = ref(null);
const currentTestingRow = ref(null);
const testResult = ref(null);

const searchForm = reactive({
  cloak_name: ''
});

const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0
});

const formData = reactive({
  cloak_name: '',
  pixel_id: '',
  access_token: '',
  backup_pixel_id: '',
  backup_access_token: '',
  load_report_enabled: false,
  load_report_event: 'PageView',
  load_report_value: null,
  load_report_currency: 'USD',
  click_report_enabled: true,
  report_event: 'ViewContent',
  report_value: null,
  report_currency: 'USD',
  postback_report_enabled: false,
  postback_report_event: 'Purchase',
  postback_report_value: null,
  postback_report_currency: 'USD',
  is_enabled: true
});

const rules = computed(() => ({
  cloak_name: [{ required: true, message: '请输入斗篷名称', trigger: 'blur' }],
  report_event: [{ validator: validateReportEventName, trigger: 'change' }],
  load_report_event: [{ validator: validateReportEventName, trigger: 'change' }],
  postback_report_event: [{ validator: validateReportEventName, trigger: 'change' }],
  pixel_id: [
    { required: true, message: '请输入像素ID', trigger: 'blur' },
    { pattern: /^\d+$/, message: '像素ID必须为数字', trigger: 'blur' }
  ],
  access_token: [{ required: true, message: '请输入Token', trigger: 'blur' }],
  backup_pixel_id: [{ pattern: /^\d*$/, message: '备份像素ID必须为数字', trigger: 'blur' }],
  report_value: [
    {
      validator: (_rule, value, callback) => {
        if (formData.report_event !== 'Purchase') {
          callback();
          return;
        }
        const n = Number(value);
        if (value === null || value === undefined || Number.isNaN(n) || n <= 0) {
          callback(new Error('购物事件须填写大于 0 的金额'));
        } else {
          callback();
        }
      },
      trigger: 'change'
    }
  ],
  load_report_value: [
    {
      validator: (_rule, value, callback) => {
        if (!formData.load_report_enabled || formData.load_report_event !== 'Purchase') {
          callback();
          return;
        }
        const n = Number(value);
        if (value === null || value === undefined || Number.isNaN(n) || n <= 0) {
          callback(new Error('加载上报为 Purchase 时须填写大于 0 的金额'));
        } else {
          callback();
        }
      },
      trigger: 'change'
    }
  ],
  postback_report_value: [
    {
      validator: (_rule, value, callback) => {
        if (!formData.postback_report_enabled || formData.postback_report_event !== 'Purchase') {
          callback();
          return;
        }
        if (value === null || value === undefined || value === '') {
          callback();
          return;
        }
        const n = Number(value);
        if (Number.isNaN(n) || n <= 0) {
          callback(new Error('若填写转化固定金额须大于 0'));
        } else {
          callback();
        }
      },
      trigger: 'change'
    }
  ]
}));

/** 后端 is_usable 与 bridge_html_present 均为是否存在 HTML；兼容旧接口字段 */
const rowIsUsable = (row) =>
  row && (row.is_usable === true || row.bridge_html_present === true);

const maskToken = (token) => {
  if (!token) return '-';
  if (token.length <= 10) return '******';
  return `${token.slice(0, 6)}******${token.slice(-4)}`;
};

const formatJson = (value) => {
  if (!value) return '-';
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  return JSON.stringify(value, null, 2);
};

const fetchConfigs = async () => {
  loading.value = true;
  try {
    const resp = await getCloakConfigs({
      page: pagination.page,
      page_size: pagination.pageSize,
      ...(searchForm.cloak_name ? { cloak_name: searchForm.cloak_name } : {})
    });
    tableData.value = resp.data || [];
    pagination.total = resp.total || 0;
  } catch (error) {
    ElMessage.error(error?.message || '获取斗篷配置失败');
  } finally {
    loading.value = false;
  }
};

const resetFormData = () => {
  formData.cloak_name = '';
  formData.pixel_id = '';
  formData.access_token = '';
  formData.backup_pixel_id = '';
  formData.backup_access_token = '';
  formData.load_report_enabled = false;
  formData.load_report_event = 'PageView';
  formData.load_report_value = null;
  formData.load_report_currency = 'USD';
  formData.click_report_enabled = true;
  formData.report_event = 'ViewContent';
  formData.report_value = null;
  formData.report_currency = 'USD';
  formData.postback_report_enabled = false;
  formData.postback_report_event = 'Purchase';
  formData.postback_report_value = null;
  formData.postback_report_currency = 'USD';
  formData.is_enabled = false;
};

const handleSearch = () => {
  pagination.page = 1;
  fetchConfigs();
};

const handleReset = () => {
  searchForm.cloak_name = '';
  pagination.page = 1;
  fetchConfigs();
};

const handleCreate = () => {
  editingId.value = null;
  resetFormData();
  editDialogVisible.value = true;
};

const handleEdit = (row) => {
  editingId.value = row.id;
  formData.cloak_name = row.cloak_name;
  formData.pixel_id = row.pixel_id;
  formData.access_token = row.access_token;
  formData.backup_pixel_id = row.backup_pixel_id || '';
  formData.backup_access_token = row.backup_access_token || '';
  formData.load_report_enabled = !!row.load_report_enabled;
  formData.load_report_event = row.load_report_event || 'PageView';
  formData.load_report_value = row.load_report_value != null ? Number(row.load_report_value) : null;
  formData.load_report_currency = row.load_report_currency || 'USD';
  formData.click_report_enabled = row.click_report_enabled !== false;
  formData.report_event = row.report_event || 'ViewContent';
  formData.report_value = row.report_value != null ? Number(row.report_value) : null;
  formData.report_currency = row.report_currency || 'USD';
  formData.postback_report_enabled = !!row.postback_report_enabled;
  formData.postback_report_event = row.postback_report_event || 'Purchase';
  formData.postback_report_value =
    row.postback_report_value != null ? Number(row.postback_report_value) : null;
  formData.postback_report_currency = row.postback_report_currency || 'USD';
  formData.is_enabled = row.is_enabled;
  editDialogVisible.value = true;
};

const buildPayload = () => ({
  cloak_name: formData.cloak_name,
  pixel_id: formData.pixel_id,
  access_token: formData.access_token,
  backup_pixel_id: formData.backup_pixel_id || null,
  backup_access_token: formData.backup_access_token || null,
  load_report_enabled: !!formData.load_report_enabled,
  load_report_event: formData.load_report_event || 'PageView',
  load_report_value:
    formData.load_report_enabled && formData.load_report_event === 'Purchase'
      ? Number(formData.load_report_value)
      : null,
  load_report_currency:
    formData.load_report_enabled && formData.load_report_event === 'Purchase'
      ? (formData.load_report_currency || 'USD').trim()
      : null,
  click_report_enabled: formData.click_report_enabled !== false,
  report_event: formData.report_event || 'ViewContent',
  report_value: formData.report_event === 'Purchase' ? Number(formData.report_value) : null,
  report_currency: formData.report_event === 'Purchase' ? (formData.report_currency || 'USD').trim() : null,
  postback_report_enabled: !!formData.postback_report_enabled,
  postback_report_event: formData.postback_report_event || 'Purchase',
  postback_report_value:
    formData.postback_report_enabled &&
    formData.postback_report_event === 'Purchase' &&
    formData.postback_report_value != null &&
    formData.postback_report_value !== ''
      ? Number(formData.postback_report_value)
      : null,
  postback_report_currency:
    formData.postback_report_enabled && formData.postback_report_event === 'Purchase'
      ? (formData.postback_report_currency || 'USD').trim()
      : null,
  is_enabled: formData.is_enabled
});

const handleSave = async () => {
  try {
    await formRef.value?.validate();
    saving.value = true;
    if (editingId.value) {
      await updateCloakConfig(editingId.value, buildPayload());
      ElMessage.success('斗篷配置更新成功');
    } else {
      await createCloakConfig(buildPayload());
      ElMessage.success('斗篷配置创建成功');
    }
    editDialogVisible.value = false;
    fetchConfigs();
  } catch (error) {
    ElMessage.error(error?.message || '保存斗篷配置失败');
  } finally {
    saving.value = false;
  }
};

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除斗篷配置「${row.cloak_name}」吗？`, '删除确认', {
      type: 'warning'
    });
    await deleteCloakConfig(row.id);
    ElMessage.success('删除成功');
    fetchConfigs();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.message || '删除失败');
    }
  }
};

const handleToggle = async (row, value) => {
  if (value && !rowIsUsable(row)) {
    ElMessage.warning('请先上传对应桥页 HTML，检测到文件后方可开启斗篷');
    return;
  }
  const oldValue = row.is_enabled;
  row.is_enabled = value;
  try {
    await updateCloakConfig(row.id, { is_enabled: value });
    ElMessage.success(`已${value ? '开启' : '关闭'}斗篷配置`);
    fetchConfigs();
  } catch (error) {
    row.is_enabled = oldValue;
    ElMessage.error(error?.message || '更新开关失败');
  }
};

const handleOpenUpload = (row) => {
  uploadTargetRow.value = row;
  uploadSelectedFile.value = null;
  uploadDialogKey.value += 1;
  uploadDialogVisible.value = true;
};

const handleHtmlFileChange = (uploadFile) => {
  uploadSelectedFile.value = uploadFile?.raw || null;
};

const handleHtmlExceed = (files) => {
  const raw = files?.[0];
  uploadSelectedFile.value = raw || null;
};

const handleUploadDialogClosed = () => {
  uploadTargetRow.value = null;
  uploadSelectedFile.value = null;
};

const submitBridgeHtml = async () => {
  if (!uploadTargetRow.value?.id) {
    ElMessage.warning('无效的斗篷配置');
    return;
  }
  if (!uploadSelectedFile.value) {
    ElMessage.warning('请选择 HTML 文件');
    return;
  }
  uploading.value = true;
  try {
    await uploadCloakBridgeHtml(uploadTargetRow.value.id, uploadSelectedFile.value);
    ElMessage.success('桥页 HTML 上传成功');
    uploadDialogVisible.value = false;
    fetchConfigs();
  } catch (error) {
    ElMessage.error(error?.message || '上传失败');
  } finally {
    uploading.value = false;
  }
};

const handleTestReport = async (row) => {
  try {
    if (row.report_event === 'Purchase' && (row.report_value == null || Number(row.report_value) <= 0)) {
      ElMessage.warning('当前斗篷为购物事件，请先在编辑中保存有效金额后再测上报');
      return;
    }
    currentTestingRow.value = row;
    const result = await testCloakReport(row.id, {
      adsid: `test-${Date.now()}`,
      email: 'test@example.com',
      phone: '13800138000',
      ip: '127.0.0.1',
      ua: navigator.userAgent || 'Mozilla/5.0',
      use_hash: true
    });
    testResult.value = result;
    testDialogVisible.value = true;
  } catch (error) {
    ElMessage.error(error?.message || '测试上报失败');
  }
};

watch(
  () => [pagination.page, pagination.pageSize],
  () => {
    fetchConfigs();
  }
);

onMounted(() => {
  fetchConfigs();
});
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
