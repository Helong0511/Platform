<template>
  <div class="cloak-management">
    <div class="page-header">
      <h2>斗篷管理</h2>
      <p>管理斗篷名称、像素与 Token，并支持测试上报</p>
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
        <el-table-column prop="pixel_id" label="像素ID" min-width="150" />
        <el-table-column label="Token" min-width="160">
          <template #default="{ row }">
            <span>{{ maskToken(row.access_token) }}</span>
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
            <el-switch :model-value="row.is_enabled" @change="(val) => handleToggle(row, val)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="handleEdit(row)">编辑</el-button>
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
      width="760px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="formData" :rules="rules" label-width="120px">
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
        <el-form-item label="开关" prop="is_enabled">
          <el-switch v-model="formData.is_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="testDialogVisible"
      title="测试上报结果"
      width="900px"
      :close-on-click-modal="false"
    >
      <el-alert type="info" :closable="false" style="margin-bottom: 12px;">
        当前斗篷：{{ currentTestingRow?.cloak_name || '-' }}
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
import { Plus, Refresh, Search } from '@element-plus/icons-vue';
import {
  createCloakConfig,
  deleteCloakConfig,
  getCloakConfigs,
  testCloakReport,
  updateCloakConfig
} from '../../api/cloak-config';

const loading = ref(false);
const saving = ref(false);
const tableData = ref([]);
const formRef = ref(null);
const editDialogVisible = ref(false);
const testDialogVisible = ref(false);
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
  is_enabled: true
});

const rules = computed(() => ({
  cloak_name: [{ required: true, message: '请输入斗篷名称', trigger: 'blur' }],
  pixel_id: [
    { required: true, message: '请输入像素ID', trigger: 'blur' },
    { pattern: /^\d+$/, message: '像素ID必须为数字', trigger: 'blur' }
  ],
  access_token: [{ required: true, message: '请输入Token', trigger: 'blur' }],
  backup_pixel_id: [{ pattern: /^\d*$/, message: '备份像素ID必须为数字', trigger: 'blur' }]
}));

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
  formData.is_enabled = true;
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
  formData.is_enabled = row.is_enabled;
  editDialogVisible.value = true;
};

const buildPayload = () => ({
  cloak_name: formData.cloak_name,
  pixel_id: formData.pixel_id,
  access_token: formData.access_token,
  backup_pixel_id: formData.backup_pixel_id || null,
  backup_access_token: formData.backup_access_token || null,
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
  const oldValue = row.is_enabled;
  row.is_enabled = value;
  try {
    await updateCloakConfig(row.id, { is_enabled: value });
    ElMessage.success(`已${value ? '开启' : '关闭'}斗篷配置`);
  } catch (error) {
    row.is_enabled = oldValue;
    ElMessage.error(error?.message || '更新开关失败');
  }
};

const handleTestReport = async (row) => {
  try {
    currentTestingRow.value = row;
    const result = await testCloakReport(row.id, {
      event: 'ViewContent',
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
