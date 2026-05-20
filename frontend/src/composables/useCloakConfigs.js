import { computed, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  createCloakConfig,
  deleteCloakConfig,
  getCloakConfigs,
  testCloakReport,
  updateCloakConfig,
  uploadCloakBridgeHtml,
} from '../api/cloak-config';
import {
  CLOAK_REPORT_EVENTS,
  formatJson,
  maskToken,
  reportEventCellLabel,
  rowIsUsable,
  validateReportEventName,
} from '../utils/cloakReportEvents';

export function useCloakConfigs() {
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

  const searchForm = reactive({ cloak_name: '' });
  const pagination = reactive({ page: 1, pageSize: 10, total: 0 });

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
    is_enabled: true,
  });

  const rules = computed(() => ({
    cloak_name: [{ required: true, message: '请输入斗篷名称', trigger: 'blur' }],
    report_event: [{ validator: validateReportEventName, trigger: 'change' }],
    load_report_event: [{ validator: validateReportEventName, trigger: 'change' }],
    postback_report_event: [{ validator: validateReportEventName, trigger: 'change' }],
    pixel_id: [
      { required: true, message: '请输入像素ID', trigger: 'blur' },
      { pattern: /^\d+$/, message: '像素ID必须为数字', trigger: 'blur' },
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
        trigger: 'change',
      },
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
        trigger: 'change',
      },
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
        trigger: 'change',
      },
    ],
  }));

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

  const fetchConfigs = async () => {
    loading.value = true;
    try {
      const resp = await getCloakConfigs({
        page: pagination.page,
        page_size: pagination.pageSize,
        ...(searchForm.cloak_name ? { cloak_name: searchForm.cloak_name } : {}),
      });
      tableData.value = resp.data || [];
      pagination.total = resp.total || 0;
    } catch (error) {
      ElMessage.error(error?.message || '获取斗篷配置失败');
    } finally {
      loading.value = false;
    }
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
    formData.load_report_value =
      row.load_report_value != null ? Number(row.load_report_value) : null;
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
    report_currency:
      formData.report_event === 'Purchase' ? (formData.report_currency || 'USD').trim() : null,
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
    is_enabled: formData.is_enabled,
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
        type: 'warning',
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
    uploadSelectedFile.value = files?.[0] || null;
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
        use_hash: true,
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
    },
  );

  onMounted(() => {
    fetchConfigs();
  });

  return {
    CLOAK_REPORT_EVENTS,
    loading,
    saving,
    tableData,
    formRef,
    editDialogVisible,
    testDialogVisible,
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
  };
}
