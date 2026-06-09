/**
 * 斗篷管理页组合式逻辑（useCloakConfigs）
 *
 * 职责：
 * - 分页列表与搜索
 * - 新建/编辑表单（载/点/转三阶段上报、Purchase 金额校验）
 * - 桥页 HTML 上传、启用开关（须磁盘存在对应 .html）
 * - 分阶段测试 CAPI 上报并展示主/备像素响应
 */
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
  CLOAK_TEST_REPORT_PHASES,
  formatJson,
  getTestPhaseEventMeta,
  maskToken,
  reportEventCellLabel,
  rowIsUsable,
  validateReportEventName,
  validateTestReportPhase,
} from '../utils/cloakReportEvents';

/**
 * 斗篷管理页组合式函数：集中管理列表、表单、上传、测试上报的全部状态与事件。
 * 供 CloakManagement.vue 解构使用，保持 Vue 组件仅负责模板渲染。
 */
export function useCloakConfigs() {
  // ---------- 列表与加载状态 ----------
  const loading = ref(false); // 表格数据请求中
  const saving = ref(false); // 编辑弹窗保存中
  const tableData = ref([]); // 当前页斗篷配置行

  // ---------- 编辑弹窗 ----------
  const formRef = ref(null); // Element Plus 表单实例，保存前调用 validate()
  const editDialogVisible = ref(false);
  const editingId = ref(null); // null=新建，数字=编辑已有配置 id

  // ---------- 测试上报弹窗（两步骤：选阶段 → 看结果） ----------
  const testDialogVisible = ref(false); // 展示 CAPI 请求/响应详情
  const testPhaseDialogVisible = ref(false); // 选择 load/click/postback 阶段
  const testPhase = ref('postback'); // 当前选中的测试阶段，默认转化
  const testPhaseTargetRow = ref(null); // 待测试的表格行
  const testSubmitting = ref(false);
  const currentTestingRow = ref(null);
  const testResult = ref(null); // testCloakReport API 返回的 primary/backup 详情

  // ---------- 桥页 HTML 上传弹窗 ----------
  const uploadDialogVisible = ref(false);
  const uploadDialogKey = ref(0); // 递增以强制 el-upload 重新挂载，清空已选文件
  const uploadTargetRow = ref(null);
  const uploadSelectedFile = ref(null); // el-upload on-change 得到的 raw File
  const uploading = ref(false);

  // ---------- 搜索与分页 ----------
  const searchForm = reactive({ cloak_name: '' });
  const pagination = reactive({ page: 1, pageSize: 10, total: 0 });

  // 编辑表单数据，字段与后端 CloakConfigCreate / CloakConfigUpdate 对齐
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

  // 表单校验：与后端 app/schemas/cloak.py 规则对齐
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

  /** 重置编辑弹窗为新建默认值（新建时 is_enabled 默认关闭，须先上传 HTML 再开启） */
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

  /** 按当前表单与 Purchase 规则组装提交体（非 Purchase 阶段不传金额/货币） */
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

  /** 列表开关：无桥页文件时不允许开启 */
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

  const handleTestReport = (row) => {
    testPhaseTargetRow.value = row;
    testPhase.value = 'postback';
    testPhaseDialogVisible.value = true;
  };

  const submitTestReport = async () => {
    const row = testPhaseTargetRow.value;
    if (!row?.id) {
      ElMessage.warning('无效的斗篷配置');
      return;
    }
    const phaseWarning = validateTestReportPhase(row, testPhase.value);
    if (phaseWarning) {
      ElMessage.warning(phaseWarning);
      return;
    }
    testSubmitting.value = true;
    try {
      currentTestingRow.value = row;
      const result = await testCloakReport(row.id, {
        report_phase: testPhase.value,
        adsid: `test-${Date.now()}`,
        email: 'test@example.com',
        phone: '13800138000',
        ip: '127.0.0.1',
        ua: navigator.userAgent || 'Mozilla/5.0',
        use_hash: true,
      });
      testResult.value = result;
      testPhaseDialogVisible.value = false;
      testDialogVisible.value = true;
    } catch (error) {
      ElMessage.error(error?.message || '测试上报失败');
    } finally {
      testSubmitting.value = false;
    }
  };

  const currentTestPhaseLabel = computed(() => {
    const phase = testResult.value?.report_phase || testPhase.value;
    return CLOAK_TEST_REPORT_PHASES.find((o) => o.value === phase)?.label || phase;
  });

  const currentTestEventMeta = computed(() => {
    if (testResult.value?.report_event) {
      return {
        event: testResult.value.report_event,
        value: testResult.value.report_value,
        currency: testResult.value.report_currency || 'USD',
      };
    }
    return getTestPhaseEventMeta(currentTestingRow.value, testPhase.value);
  });

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
  };
}
