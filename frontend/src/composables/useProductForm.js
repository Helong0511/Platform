/**
 * 组合式函数 - 产品表单：创建/编辑/转移
 * @file composables/useProductForm.js
 */
import { ref, watch, reactive, computed } from 'vue';
import { ElMessage } from 'element-plus';
import { getAvailableProductNames, getProductDetail, getProductAssignments } from '../api/product';
import { getClientDetail } from '../api/client';
import { logger } from '../utils/logger';
import { formatDate } from '../utils/dateFormat';
import {
  addDaysToDateString,
  formatClientFullName,
  formatProductOptionLabel,
  getTodayDateString,
  getYesterdayDateString,
  toDateStringOnly,
} from '../utils/productClientFormat';

function createEmptyFormData() {
  return {
    name: '',
    ecpm_deduct_ratio: 0,
    revenue_deduct_ratio: 0,
    is_active: true,
    downstream_postback_url: '',
    downstream_postback_method: 'GET',
    downstream_postback_success_check: '',
    notification_address: '',
  };
}

/**
 * 产品添加/编辑表单及客户转移逻辑
 */
export function useProductForm(props, emit) {
  const formDialogVisible = ref(false);
  const formTitle = ref('添加产品');
  const saving = ref(false);
  const currentProductId = ref(null);
  const formDialogRef = ref(null);

  const transferDateDialogVisible = ref(false);
  const transferDateForm = reactive({
    oldClientId: null,
    oldClientName: '',
    oldClientFullInfo: null,
    startDate: null,
    lastClientEndDate: null,
  });
  const pendingTransferData = ref(null);
  const productAssignments = ref([]);
  const loadingAssignments = ref(false);
  const lastClientStartDate = ref(null);
  const clientDetailCache = ref(new Map());
  const productAssignmentsCache = ref(new Map());
  const fetchingClientDetail = ref(new Set());
  const fetchingAssignments = ref(new Set());

  const oldClientEndDate = computed(() => {
    if (transferDateForm.lastClientEndDate) {
      return transferDateForm.lastClientEndDate;
    }
    if (!transferDateForm.startDate) {
      return '';
    }
    const startDate = new Date(transferDateForm.startDate);
    startDate.setDate(startDate.getDate() - 1);
    const year = startDate.getFullYear();
    const month = String(startDate.getMonth() + 1).padStart(2, '0');
    const day = String(startDate.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  });

  const productNames = ref([]);
  const productNamesLoading = ref(false);
  /** 当前 productNames 对应的客户 ID，换客户时须重拉 */
  const loadedNamesClientId = ref(null);
  const productNameBackup = ref('');
  const selectedProduct = ref(null);

  const formData = reactive(createEmptyFormData());

  watch(() => formData.name, (newValue) => {
    if (newValue && String(newValue).trim() !== '') {
      const trimmedValue = String(newValue).trim();
      if (trimmedValue !== productNameBackup.value) {
        productNameBackup.value = trimmedValue;
      }
    }
  }, { immediate: true });

  const formRules = {
    name: [
      { required: true, message: '请输入产品名称', trigger: 'blur' },
      { min: 2, max: 100, message: '产品名称长度在 2 到 100 个字符', trigger: 'blur' },
    ],
    ecpm_deduct_ratio: [
      { required: true, message: '请输入eCPM减扣比例', trigger: 'blur' },
      { type: 'number', min: 0, max: 1, message: 'eCPM减扣比例范围：0.00 - 1.00', trigger: 'blur' },
    ],
    revenue_deduct_ratio: [
      { required: true, message: '请输入收益减扣比例', trigger: 'blur' },
      { type: 'number', min: 0, max: 1, message: '收益减扣比例范围：0.00 - 1.00', trigger: 'blur' },
    ],
  };

  const getFormRefs = () => ({
    formRef: formDialogRef.value?.formRef,
    productNameSelectRef: formDialogRef.value?.productNameSelectRef,
  });

  const clearFormValidation = () => {
    getFormRefs().formRef?.clearValidate();
  };

  const queryProductNames = (queryString, cb) => {
    if (productNames.value.length === 0 && !productNamesLoading.value) {
      loadProductNames().then(() => {
        filterAndReturnSuggestions(queryString, cb);
      });
    } else {
      filterAndReturnSuggestions(queryString, cb);
    }
  };

  const buildProductSuggestion = (product) => ({
    value: product.name,
    label: formatProductOptionLabel(product),
    product,
  });

  const filterAndReturnSuggestions = (queryString, cb) => {
    const normalizedQuery = queryString?.trim().toLowerCase() || '';
    const matchProduct = (product) => {
      if (!normalizedQuery) return true;
      const label = formatProductOptionLabel(product).toLowerCase();
      return product.name.toLowerCase().includes(normalizedQuery)
        || label.includes(normalizedQuery);
    };

    const results = productNames.value
      .filter(matchProduct)
      .map(buildProductSuggestion);

    if (normalizedQuery) {
      const exists = results.some((item) => item.value === queryString.trim());
      if (!exists) {
        results.unshift({
          value: queryString.trim(),
          label: queryString.trim(),
          product: null,
        });
      }
    }

    cb(results);
  };

  /**
   * 加载可选产品名；按客户缓存，换客户或 force 时重新请求。
   * @param {boolean} [force=false]
   */
  const loadProductNames = async (force = false) => {
    const clientId = props.clientId ?? null;
    if (
      !force &&
      productNames.value.length > 0 &&
      loadedNamesClientId.value === clientId
    ) {
      return;
    }

    try {
      productNamesLoading.value = true;
      const result = await getAvailableProductNames(clientId);
      productNames.value = result.data || [];
      loadedNamesClientId.value = clientId;
    } catch {
      productNames.value = [];
      loadedNamesClientId.value = null;
    } finally {
      productNamesLoading.value = false;
    }
  };

  watch(
    () => props.clientId,
    (next, prev) => {
      if (next !== prev) {
        productNames.value = [];
        loadedNamesClientId.value = null;
      }
    }
  );

  const fetchClientDetailCached = async (clientId) => {
    if (clientDetailCache.value.has(clientId)) {
      return clientDetailCache.value.get(clientId);
    }
    if (fetchingClientDetail.value.has(clientId)) {
      let retries = 0;
      while (fetchingClientDetail.value.has(clientId) && retries < 10) {
        await new Promise((resolve) => setTimeout(resolve, 100));
        retries++;
        if (clientDetailCache.value.has(clientId)) {
          return clientDetailCache.value.get(clientId);
        }
      }
      return null;
    }

    fetchingClientDetail.value.add(clientId);
    try {
      const clientDetail = await getClientDetail(clientId, { silent: true, useCache: true });
      if (clientDetail) {
        clientDetailCache.value.set(clientId, clientDetail);
      }
      return clientDetail;
    } catch (error) {
      logger.warn('获取客户详情失败:', error);
      if (error.response?.status !== 429) {
        clientDetailCache.value.set(clientId, null);
      }
      return null;
    } finally {
      fetchingClientDetail.value.delete(clientId);
    }
  };

  const setupTransferFormFromProduct = async (product, oldClientFullInfo) => {
    transferDateForm.oldClientId = product.client_id;
    transferDateForm.oldClientName = oldClientFullInfo ? formatClientFullName(oldClientFullInfo) : '未知客户';
    transferDateForm.oldClientFullInfo = oldClientFullInfo;
    transferDateForm.startDate = getTodayDateString();
    transferDateForm.lastClientEndDate = getYesterdayDateString();
    await fetchProductAssignments(product.id, true);
  };

  const clearTransferState = () => {
    pendingTransferData.value = null;
    transferDateForm.oldClientId = null;
    transferDateForm.oldClientName = '';
    transferDateForm.oldClientFullInfo = null;
    transferDateForm.startDate = null;
    transferDateForm.lastClientEndDate = null;
    productAssignments.value = [];
    lastClientStartDate.value = null;
  };

  const handleProductNameSelect = async (item) => {
    if (!item?.value) {
      return;
    }

    const selectedValue = String(item.value).trim();
    productNameBackup.value = selectedValue;
    formData.name = selectedValue;

    if (item.product) {
      selectedProduct.value = item.product;

      if (selectedProduct.value.client_id !== props.clientId) {
        try {
          const originalProduct = await getProductDetail(selectedProduct.value.id, { silent: true });
          if (originalProduct) {
            formData.ecpm_deduct_ratio = originalProduct.ecpm_deduct_ratio || 0;
            formData.revenue_deduct_ratio = originalProduct.revenue_deduct_ratio || 0;
          }

          const oldClientFullInfo = await fetchClientDetailCached(selectedProduct.value.client_id);
          await setupTransferFormFromProduct(selectedProduct.value, oldClientFullInfo);
        } catch (error) {
          logger.warn('handleProductNameSelect: 获取原产品信息失败:', error);
        }
      } else {
        clearTransferState();
        selectedProduct.value = item.product;
      }
    } else {
      selectedProduct.value = null;
      clearTransferState();
    }
  };

  const handleProductNameBlur = () => {
    if (formData.name && formData.name.trim() !== '') {
      productNameBackup.value = String(formData.name).trim();
      const matchedProduct = productNames.value.find((p) => p.name === productNameBackup.value);
      selectedProduct.value = matchedProduct || null;
    } else if (productNameBackup.value?.trim()) {
      formData.name = productNameBackup.value;
    }
  };

  const resetFormAfterSave = () => {
    Object.assign(formData, createEmptyFormData());
    currentProductId.value = null;
    productNames.value = [];
    loadedNamesClientId.value = null;
    selectedProduct.value = null;
    clearTransferState();
  };

  const handleAdd = async () => {
    currentProductId.value = null;
    formTitle.value = '添加产品';
    Object.assign(formData, createEmptyFormData());
    productNameBackup.value = '';
    selectedProduct.value = null;
    clearTransferState();
    await loadProductNames(true);
    clearFormValidation();
    formDialogVisible.value = true;
  };

  const handleEdit = async (product) => {
    currentProductId.value = product.id;
    formTitle.value = '编辑产品';
    await loadProductNames(true);
    Object.assign(formData, {
      name: product.name || '',
      ecpm_deduct_ratio: product.ecpm_deduct_ratio || 0,
      revenue_deduct_ratio: product.revenue_deduct_ratio || 0,
      is_active: product.is_active !== undefined ? product.is_active : true,
      downstream_postback_url: product.downstream_postback_url || '',
      downstream_postback_method: product.downstream_postback_method || 'GET',
      downstream_postback_success_check: product.downstream_postback_success_check || '',
      notification_address: product.notification_address || '',
    });
    clearFormValidation();
    formDialogVisible.value = true;
  };

  const resolveProductNameForSave = () => {
    const { formRef, productNameSelectRef } = getFormRefs();
    let productName = '';

    if (productNameSelectRef?.value) {
      try {
        let refValue = productNameSelectRef.value.selectedLabel
          || productNameSelectRef.value.value
          || productNameSelectRef.value.selected?.label;

        if (!refValue && productNameSelectRef.value.$el) {
          const $el = productNameSelectRef.value.$el;
          if ($el && typeof $el.querySelector === 'function') {
            const inputElement = $el.querySelector('.el-input__inner');
            if (inputElement?.value) {
              refValue = inputElement.value;
            }
          }
        }

        if (refValue && String(refValue).trim() !== '') {
          productName = String(refValue).trim();
        }
      } catch (e) {
        logger.warn('handleSave: 从 ref 获取值失败:', e);
      }
    }

    if (!productName) {
      const selectInput = document.querySelector('.product-name-select .el-input__inner');
      if (selectInput?.value?.trim()) {
        productName = selectInput.value.trim();
      }
    }

    if (!productName && formData.name && String(formData.name).trim() !== '') {
      productName = String(formData.name).trim();
    }

    if (productName) {
      formData.name = productName;
      return productName;
    }

    logger.error('handleSave: 无法获取产品名称，所有方法都失败');
    ElMessage.error('请输入产品名称');
    return null;
  };

  const emitSaveAndWait = (productId, submitData) => new Promise((resolve, reject) => {
    let callbackCalled = false;
    emit('save', {
      id: productId,
      data: submitData,
      callback: (success) => {
        callbackCalled = true;
        if (success) {
          resolve(true);
        } else {
          reject(new Error('保存失败'));
        }
      },
    });

    setTimeout(() => {
      if (!callbackCalled) {
        logger.error('handleSave: 保存操作超时，回调未执行');
        reject(new Error('保存操作超时'));
      }
    }, 10000);
  });

  const prepareTransferIfNeeded = async () => {
    let productIdToUpdate = currentProductId.value;
    let isTransferProduct = false;

    if (pendingTransferData.value?.endDate) {
      isTransferProduct = true;
      productIdToUpdate = pendingTransferData.value.productId;
      return { productIdToUpdate, isTransferProduct, needsDateDialog: false };
    }

    if (!selectedProduct.value || selectedProduct.value.client_id === props.clientId) {
      return { productIdToUpdate, isTransferProduct, needsDateDialog: false };
    }

    if (!pendingTransferData.value || pendingTransferData.value.productId !== selectedProduct.value.id) {
      try {
        const oldClientFullInfo = await fetchClientDetailCached(selectedProduct.value.client_id);
        const oldClientName = oldClientFullInfo ? formatClientFullName(oldClientFullInfo) : '未知客户';

        pendingTransferData.value = {
          productId: selectedProduct.value.id,
          oldClientId: selectedProduct.value.client_id,
          oldClientName,
          oldClientFullInfo,
          newClientId: props.clientId,
          newClientName: props.clientName,
          productName: selectedProduct.value.name,
        };

        transferDateForm.oldClientId = selectedProduct.value.client_id;
        transferDateForm.oldClientName = oldClientName;
        transferDateForm.oldClientFullInfo = oldClientFullInfo;
        transferDateForm.startDate = getTodayDateString();
        transferDateForm.lastClientEndDate = getYesterdayDateString();

        await fetchProductAssignments(selectedProduct.value.id);
      } catch (error) {
        logger.warn('设置转移数据失败:', error);
      }
    }

    // 选择其他客户产品时仅预填日期，须用户确认后才视为转移完成
    if (!pendingTransferData.value?.endDate) {
      productIdToUpdate = selectedProduct.value.id;
      if (productAssignments.value.length === 0) {
        try {
          await fetchProductAssignments(selectedProduct.value.id, true);
        } catch (error) {
          logger.warn('打开日期选择对话框时获取产品分配历史失败:', error);
        }
      }
      return { productIdToUpdate, isTransferProduct: true, needsDateDialog: true };
    }

    productIdToUpdate = pendingTransferData.value.productId;
    return { productIdToUpdate, isTransferProduct: true, needsDateDialog: false };
  };

  const buildSubmitData = (isTransferProduct) => {
    const submitData = {
      name: String(formData.name).trim(),
      ecpm_deduct_ratio: formData.ecpm_deduct_ratio,
      revenue_deduct_ratio: formData.revenue_deduct_ratio,
      is_active: formData.is_active,
      downstream_postback_url: formData.downstream_postback_url ? String(formData.downstream_postback_url).trim() : null,
      downstream_postback_method: formData.downstream_postback_method || 'GET',
      downstream_postback_success_check: formData.downstream_postback_success_check
        ? String(formData.downstream_postback_success_check).trim()
        : null,
      notification_address: formData.notification_address ? String(formData.notification_address).trim() : null,
      client_id: props.clientId,
    };

    // 仅在实际执行产品转移时剥离创建字段，避免残留转移状态误删产品名称
    if (isTransferProduct && pendingTransferData.value) {
      delete submitData.name;
      delete submitData.ecpm_deduct_ratio;
      delete submitData.revenue_deduct_ratio;
      delete submitData.is_active;
      delete submitData.downstream_postback_url;
      delete submitData.downstream_postback_method;
      delete submitData.downstream_postback_success_check;
      delete submitData.notification_address;

      if (pendingTransferData.value.startDate) {
        submitData.transfer_date = pendingTransferData.value.startDate;
      }
      if (pendingTransferData.value.endDate) {
        submitData.old_client_end_date = pendingTransferData.value.endDate;
      }
    }

    return submitData;
  };

  const validateSubmitData = (submitData, isTransferProduct) => {
    if (!isTransferProduct) {
      if (!submitData.name?.trim()) {
        logger.error('handleSave: 提交数据中产品名称为空');
        ElMessage.error('请输入产品名称');
        return false;
      }
      if (submitData.ecpm_deduct_ratio === undefined || submitData.ecpm_deduct_ratio === null) {
        ElMessage.error('请输入eCPM减扣比例');
        return false;
      }
      if (submitData.revenue_deduct_ratio === undefined || submitData.revenue_deduct_ratio === null) {
        ElMessage.error('请输入收益减扣比例');
        return false;
      }
      return true;
    }

    if (!submitData.client_id) {
      logger.error('handleSave: 客户ID为空');
      ElMessage.error('客户ID不能为空');
      return false;
    }
    return true;
  };

  const handleSave = async () => {
    const { formRef } = getFormRefs();
    if (!formRef) {
      logger.error('handleSave: formRef 不存在');
      return;
    }

    const savedProductName = resolveProductNameForSave();
    if (!savedProductName) {
      return;
    }

    try {
      await formRef.validate();

      if (!formData.name || String(formData.name).trim() === '') {
        if (savedProductName) {
          formData.name = savedProductName;
          await formRef.validate();
        } else {
          logger.error('handleSave: 产品名称为空且无法恢复');
          ElMessage.error('请输入产品名称');
          return;
        }
      }

      const { productIdToUpdate, isTransferProduct, needsDateDialog } = await prepareTransferIfNeeded();
      if (needsDateDialog) {
        transferDateDialogVisible.value = true;
        return;
      }

      saving.value = true;

      const submitData = buildSubmitData(isTransferProduct);
      if (!validateSubmitData(submitData, isTransferProduct)) {
        saving.value = false;
        return;
      }

      const finalProductId = productIdToUpdate || currentProductId.value;
      await emitSaveAndWait(finalProductId, submitData);

      formDialogVisible.value = false;
      resetFormAfterSave();
    } catch (error) {
      if (!formData.name && savedProductName) {
        formData.name = savedProductName;
      }
    } finally {
      saving.value = false;
    }
  };

  const handleStartDateChange = (value) => {
    transferDateForm.startDate = value;
    if (value) {
      const startDate = new Date(value);
      startDate.setDate(startDate.getDate() - 1);
      const year = startDate.getFullYear();
      const month = String(startDate.getMonth() + 1).padStart(2, '0');
      const day = String(startDate.getDate()).padStart(2, '0');
      transferDateForm.lastClientEndDate = `${year}-${month}-${day}`;
    }
  };

  const handleEndDateChange = (value) => {
    transferDateForm.lastClientEndDate = value;
    if (value) {
      const endDate = new Date(value);
      endDate.setDate(endDate.getDate() + 1);
      const year = endDate.getFullYear();
      const month = String(endDate.getMonth() + 1).padStart(2, '0');
      const day = String(endDate.getDate()).padStart(2, '0');
      transferDateForm.startDate = `${year}-${month}-${day}`;
    }
  };

  const fetchProductAssignments = async (productId, useCache = false) => {
    if (!productId) {
      return;
    }

    const applyAssignments = (assignments) => {
      productAssignments.value = assignments;
      if (assignments.length > 0) {
        const currentAssignment = assignments.find((a) => !a.end_date) || assignments[0];
        if (currentAssignment) {
          lastClientStartDate.value = currentAssignment.start_date;
        }
      }
    };

    if (useCache && productAssignmentsCache.value.has(productId)) {
      applyAssignments(productAssignmentsCache.value.get(productId));
      return;
    }

    if (fetchingAssignments.value.has(productId)) {
      let retries = 0;
      while (fetchingAssignments.value.has(productId) && retries < 10) {
        await new Promise((resolve) => setTimeout(resolve, 100));
        retries++;
        if (productAssignmentsCache.value.has(productId)) {
          applyAssignments(productAssignmentsCache.value.get(productId));
          return;
        }
      }
    }

    loadingAssignments.value = true;
    fetchingAssignments.value.add(productId);

    try {
      const result = await getProductAssignments(productId);
      let assignments = [];
      if (result?.data) {
        if (Array.isArray(result.data)) {
          assignments = result.data;
        } else if (result.data.data && Array.isArray(result.data.data)) {
          assignments = result.data.data;
        }
      }

      assignments.sort((a, b) => new Date(b.start_date) - new Date(a.start_date));
      applyAssignments(assignments);

      if (productAssignmentsCache.value.size >= 10) {
        const firstKey = productAssignmentsCache.value.keys().next().value;
        productAssignmentsCache.value.delete(firstKey);
      }
      productAssignmentsCache.value.set(productId, assignments);

      if (assignments.length > 0) {
        logger.info(`成功获取产品 ${productId} 的分配历史，共 ${assignments.length} 条记录`);
      } else {
        logger.warn(`产品 ${productId} 没有分配历史记录`);
      }
    } catch (error) {
      logger.warn('获取产品分配历史失败:', error);
      productAssignments.value = [];
      if (error.response?.status !== 429) {
        productAssignmentsCache.value.set(productId, []);
      }
    } finally {
      loadingAssignments.value = false;
      fetchingAssignments.value.delete(productId);
    }
  };

  const continueSaveAfterDateSelection = async () => {
    if (!pendingTransferData.value?.startDate || !pendingTransferData.value?.endDate) {
      ElMessage.error('转移日期数据不完整，请重新操作');
      return;
    }

    saving.value = true;

    try {
      const submitData = {
        client_id: props.clientId,
        transfer_date: pendingTransferData.value.startDate,
        old_client_end_date: pendingTransferData.value.endDate,
      };

      await emitSaveAndWait(pendingTransferData.value.productId, submitData);
      formDialogVisible.value = false;
      resetFormAfterSave();
    } catch (error) {
      logger.error('continueSaveAfterDateSelection: 保存失败:', error);
    } finally {
      saving.value = false;
    }
  };

  const confirmTransferDate = async () => {
    const startDateStr = toDateStringOnly(transferDateForm.startDate);
    if (!startDateStr) {
      ElMessage.warning('请选择开始日期');
      return;
    }

    if (startDateStr > getTodayDateString()) {
      ElMessage.warning('开始日期不能是未来日期');
      return;
    }

    const lastClientEndDate = toDateStringOnly(
      transferDateForm.lastClientEndDate || getYesterdayDateString(),
    );

    const lastStartDateStr = toDateStringOnly(lastClientStartDate.value);
    if (lastStartDateStr && lastClientEndDate < lastStartDateStr) {
      ElMessage.warning(`最后一个客户的结束日期不能小于该客户的开始日期（${formatDate(lastClientStartDate.value)}）`);
      return;
    }

    // 旧客户结束日必须严格早于新客户开始日（默认：昨天 < 今天）
    if (lastClientEndDate >= startDateStr) {
      ElMessage.warning('最后一个客户的结束日期必须早于新客户的开始日期');
      return;
    }

    // 核心业务：新客户开始日 = 旧客户结束日 + 1 天（恰好相差 1 天，无空窗）
    const expectedStartDateStr = addDaysToDateString(lastClientEndDate, 1);
    if (startDateStr !== expectedStartDateStr) {
      ElMessage.warning(
        `日期连续性错误：新客户开始日期（${startDateStr}）必须是旧客户结束日期（${lastClientEndDate}）+ 1天，`
        + `期望值：${expectedStartDateStr}，以确保广告数据无空窗期`,
      );
      return;
    }

    if (pendingTransferData.value) {
      pendingTransferData.value.startDate = transferDateForm.startDate;
      pendingTransferData.value.endDate = lastClientEndDate;
    }

    transferDateDialogVisible.value = false;
    await continueSaveAfterDateSelection();
  };

  return {
    formDialogRef,
    formDialogVisible,
    formTitle,
    saving,
    formData,
    formRules,
    productNames,
    productNamesLoading,
    queryProductNames,
    transferDateDialogVisible,
    transferDateForm,
    productAssignments,
    loadingAssignments,
    lastClientStartDate,
    oldClientEndDate,
    handleAdd,
    handleEdit,
    handleSave,
    handleProductNameSelect,
    handleProductNameBlur,
    loadProductNames,
    handleStartDateChange,
    handleEndDateChange,
    confirmTransferDate,
  };
}
