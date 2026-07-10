/**
 * GAM 多账号调度配置（账号 + 白名单 + 每账号报表类型）
 * @file composables/useGamSchedulerConfig.js
 */
import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  getGamSchedulerConfig,
  saveGamSchedulerConfig,
  uploadGamCredentials,
  refreshGamReportTypes,
} from '../api/scheduled-task';
import { GAM_SCHEDULED_TASK_NAME } from '../constants/scheduledTasks';
import { extractErrorMessage, isErrorHandled } from '../utils/api';
import {
  mergeGamProductNames,
  parseGamProductNamesFromText,
} from '../utils/gamProductWhitelist';

const DEFAULT_REPORT_KEYS = ['ad_unit', 'country', 'site'];

/** 前端本地账号实例 ID，用于 v-for key 与按索引删除（与可编辑的 key 字段解耦） */
let gamAccountLocalIdSeq = 0;

function nextGamAccountLocalId() {
  gamAccountLocalIdSeq += 1;
  return gamAccountLocalIdSeq;
}

function createEmptyAccount(index = 1, defaultReportOptions = []) {
  return {
    _localId: nextGamAccountLocalId(),
    key: `account_${index}`,
    credentials_json: '',
    application_name: '',
    report_keys: [...DEFAULT_REPORT_KEYS],
    report_type_options: [...defaultReportOptions],
    reportTypesNetworkLabel: '',
    product_whitelist: [],
    network_code: '',
    credentials_exists: false,
    credentialsUploading: false,
    reportTypesRefreshing: false,
    fetch_all: true,
  };
}

function cloneAccount(account, defaultReportOptions = []) {
  const options = account.report_type_options?.length
    ? account.report_type_options
    : defaultReportOptions;
  return {
    ...account,
    _localId: account._localId || nextGamAccountLocalId(),
    report_keys: [...(account.report_keys || DEFAULT_REPORT_KEYS)],
    report_type_options: [...(options || [])],
    reportTypesNetworkLabel: account.reportTypesNetworkLabel || '',
    product_whitelist: [...(account.product_whitelist || [])],
    credentialsUploading: false,
    reportTypesRefreshing: false,
  };
}

function parseNetworkCodeFromFilename(filename) {
  const base = String(filename || '').split(/[/\\]/).pop() || '';
  const match = /^gam-(\d+)\.json$/i.exec(base);
  return match ? match[1] : '';
}

function applyRefreshedReportTypes(account, data) {
  if (!Array.isArray(data?.report_types) || !data.report_types.length) {
    return;
  }
  account.report_type_options = [...data.report_types];
  const validKeys = new Set(data.report_types.map((item) => item.key));
  const kept = (account.report_keys || []).filter((key) => validKeys.has(key));
  account.report_keys = kept.length
    ? kept
    : data.report_types
        .map((item) => item.key)
        .filter((key) => key !== 'daily' || !(account.product_whitelist || []).length);
  if (!account.report_keys.length) {
    account.report_keys = [data.report_types[0].key];
  }
  const networkName = data.network_display_name || data.network_code || '';
  account.reportTypesNetworkLabel = networkName
    ? `${networkName}（${data.report_types.length} 种可用）`
    : `已探测 ${data.report_types.length} 种报表`;
  if (data.network_code) {
    account.network_code = data.network_code;
  }
}

export function useGamSchedulerConfig() {
  const loading = ref(false);
  const saving = ref(false);
  const configPath = ref('');
  const configExists = ref(false);
  const description = ref('');
  const defaultReportTypeOptions = ref([]);
  const accounts = ref([]);
  const unifiedMode = ref(false);
  const unifiedWhitelist = ref([]);
  const globalBulkText = ref('');
  const copySourceKey = ref('');

  /** 递增序号：丢弃过期的 load/save 响应，避免覆盖用户刚删除的账号 */
  let configSyncSeq = 0;

  const hasMultipleAccounts = () => (accounts.value || []).length > 1;

  const syncFromResponse = (data) => {
    configPath.value = data?.config_path || '';
    configExists.value = Boolean(data?.config_exists);
    description.value = data?.description || '';
    defaultReportTypeOptions.value = [...(data?.report_type_options || [])];
    accounts.value = (data?.accounts || []).map((item) =>
      cloneAccount(item, defaultReportTypeOptions.value),
    );
    if (!copySourceKey.value && accounts.value.length) {
      copySourceKey.value = accounts.value[0].key;
    }
    if (unifiedMode.value && accounts.value.length) {
      unifiedWhitelist.value = [...(accounts.value[0].product_whitelist || [])];
    }
  };

  const loadConfig = async () => {
    const seq = ++configSyncSeq;
    loading.value = true;
    try {
      const data = await getGamSchedulerConfig(GAM_SCHEDULED_TASK_NAME);
      if (seq !== configSyncSeq) return;
      syncFromResponse(data);
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
      throw error;
    } finally {
      loading.value = false;
    }
  };

  const validateAccounts = () => {
    const keys = new Set();
    for (const account of accounts.value) {
      const key = String(account.key || '').trim();
      if (!key) {
        ElMessage.warning('账号标识 key 不能为空');
        return false;
      }
      if (keys.has(key)) {
        ElMessage.warning(`重复的账号 key：${key}`);
        return false;
      }
      keys.add(key);
      if (!String(account.credentials_json || '').trim()) {
        ElMessage.warning(`账号「${key}」缺少密钥文件路径 credentials_json`);
        return false;
      }
      if (!account.report_keys?.length) {
        ElMessage.warning(`账号「${key}」请至少选择一种报表类型`);
        return false;
      }
    }
    return true;
  };

  const applyUnifiedWhitelistToAccounts = () => {
    const list = [...(unifiedWhitelist.value || [])];
    for (const account of accounts.value) {
      account.product_whitelist = [...list];
    }
  };

  const saveConfig = async () => {
    if (unifiedMode.value) {
      applyUnifiedWhitelistToAccounts();
    }
    if (!validateAccounts()) return false;

    const seq = ++configSyncSeq;
    saving.value = true;
    try {
      const data = await saveGamSchedulerConfig(GAM_SCHEDULED_TASK_NAME, {
        description: description.value,
        accounts: accounts.value.map((item) => ({
          key: String(item.key).trim(),
          credentials_json: String(item.credentials_json).trim(),
          application_name: String(item.application_name || '').trim(),
          report_keys: [...(item.report_keys || DEFAULT_REPORT_KEYS)],
          product_whitelist: item.product_whitelist || [],
        })),
      });
      if (seq !== configSyncSeq) return false;
      syncFromResponse(data);
      return true;
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
      return false;
    } finally {
      saving.value = false;
    }
  };

  const addAccount = () => {
    const nextIndex = accounts.value.length + 1;
    const account = createEmptyAccount(nextIndex, defaultReportTypeOptions.value);
    accounts.value.push(account);
    if (!copySourceKey.value) {
      copySourceKey.value = account.key;
    }
  };

  const removeAccount = async (index) => {
    const account = accounts.value[index];
    if (!account) return;

    const displayKey = String(account.key || '').trim() || `账号 ${index + 1}`;
    try {
      await ElMessageBox.confirm(
        `确定删除账号「${displayKey}」吗？删除后需点击「保存配置」才会写入配置文件。`,
        '删除账号',
        { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' },
      );
      // 使进行中的 load/save 响应失效，防止把已删账号写回列表
      configSyncSeq += 1;
      accounts.value = accounts.value.filter((_, itemIndex) => itemIndex !== index);
      if (copySourceKey.value === account.key) {
        copySourceKey.value = accounts.value[0]?.key || '';
      }
      ElMessage.success('账号已从列表移除，请点击「保存配置」生效');
    } catch (error) {
      if (error === 'cancel' || error === 'close') return;
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    }
  };

  const clearAccountWhitelist = (account) => {
    account.product_whitelist = [];
    if (unifiedMode.value) {
      unifiedWhitelist.value = [];
    }
  };

  const toggleUnifiedMode = (enabled) => {
    unifiedMode.value = enabled;
    if (enabled && accounts.value.length) {
      unifiedWhitelist.value = [...(accounts.value[0].product_whitelist || [])];
    }
  };

  const applyUnifiedWhitelist = () => {
    applyUnifiedWhitelistToAccounts();
    ElMessage.success('已同步到全部账号，请点击保存配置');
  };

  const copyWhitelistToAll = () => {
    const source = accounts.value.find((item) => item.key === copySourceKey.value);
    if (!source) {
      ElMessage.warning('请选择要复制的来源账号');
      return;
    }
    const list = [...(source.product_whitelist || [])];
    for (const account of accounts.value) {
      account.product_whitelist = [...list];
    }
    if (unifiedMode.value) {
      unifiedWhitelist.value = [...list];
    }
    ElMessage.success(`已将「${source.key}」的白名单复制到全部账号，请点击保存配置`);
  };

  const globalBulkAddToAll = () => {
    const parsed = parseGamProductNamesFromText(globalBulkText.value);
    if (!parsed.length) {
      ElMessage.warning('请先输入产品名称');
      return;
    }
    for (const account of accounts.value) {
      account.product_whitelist = mergeGamProductNames(account.product_whitelist, parsed);
    }
    if (unifiedMode.value) {
      unifiedWhitelist.value = mergeGamProductNames(unifiedWhitelist.value, parsed);
    }
    globalBulkText.value = '';
    ElMessage.success(`已向全部账号添加 ${parsed.length} 个产品名称，请点击保存配置`);
  };

  const clearAllWhitelists = async () => {
    try {
      await ElMessageBox.confirm(
        '确定将全部账号的白名单清空吗？清空后将全量拉取。',
        '全部清空',
        { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' },
      );
      for (const account of accounts.value) {
        account.product_whitelist = [];
      }
      unifiedWhitelist.value = [];
    } catch (error) {
      if (error !== 'cancel' && !isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    }
  };

  const uploadCredentialsForAccount = async (account, uploadFile) => {
    const rawFile = uploadFile?.raw || uploadFile;
    if (!rawFile) return;

    let networkCode = parseNetworkCodeFromFilename(rawFile.name);
    if (!networkCode) {
      try {
        const { value } = await ElMessageBox.prompt(
          '无法从文件名识别网络 ID，请输入 GAM 网络 ID（纯数字）',
          '填写网络 ID',
          {
            confirmButtonText: '上传',
            cancelButtonText: '取消',
            inputPattern: /^\d+$/,
            inputErrorMessage: '网络 ID 必须为纯数字',
          },
        );
        networkCode = String(value || '').trim();
      } catch (error) {
        if (error !== 'cancel' && !isErrorHandled(error)) {
          ElMessage.error(extractErrorMessage(error));
        }
        return;
      }
    }

    account.credentialsUploading = true;
    try {
      const data = await uploadGamCredentials(
        GAM_SCHEDULED_TASK_NAME,
        rawFile,
        networkCode,
      );
      account.credentials_json = data.credentials_json;
      account.network_code = data.network_code || networkCode;
      account.credentials_exists = true;
      if (data.application_name && !String(account.application_name || '').trim()) {
        account.application_name = data.application_name;
      }
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    } finally {
      account.credentialsUploading = false;
    }
  };

  const refreshReportTypesForAccount = async (account) => {
    if (!account) return;
    const credentialsJson = String(account.credentials_json || '').trim();
    if (!credentialsJson) {
      ElMessage.warning('请先填写或上传该账号的密钥文件');
      return;
    }

    account.reportTypesRefreshing = true;
    try {
      const data = await refreshGamReportTypes(GAM_SCHEDULED_TASK_NAME, {
        account_key: String(account.key || '').trim() || undefined,
        credentials_json: credentialsJson,
        application_name: String(account.application_name || '').trim() || undefined,
      });
      applyRefreshedReportTypes(account, data);
      ElMessage.success(`账号「${account.key}」报表类型已刷新`);
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    } finally {
      account.reportTypesRefreshing = false;
    }
  };

  return {
    loading,
    saving,
    configPath,
    configExists,
    description,
    defaultReportTypeOptions,
    accounts,
    unifiedMode,
    unifiedWhitelist,
    globalBulkText,
    copySourceKey,
    hasMultipleAccounts,
    loadConfig,
    saveConfig,
    addAccount,
    removeAccount,
    clearAccountWhitelist,
    toggleUnifiedMode,
    applyUnifiedWhitelist,
    copyWhitelistToAll,
    globalBulkAddToAll,
    clearAllWhitelists,
    uploadCredentialsForAccount,
    refreshReportTypesForAccount,
  };
}
