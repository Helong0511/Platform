import { computed, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import {
  getDeductionConfigs,
  createDeductionConfig,
  updateDeductionConfig,
} from '../api/deduction';
import { getAdvertisers } from '../api/advertiser';
import { getOffers } from '../api/offer';
import { getPublishers } from '../api/publisher';
import { logger } from '../utils/logger';
import {
  createConversionDeductionFormRules,
  emptyConversionDeductionForm,
} from '../utils/conversionDeductionFormRules';

/**
 * 转化扣减配置新增/编辑对话框。
 * @param {{ fetchData: () => Promise<void> }} deps
 */
export function useConversionDeductionForm({ fetchData }) {
  const dialogVisible = ref(false);
  const dialogMode = ref('add');
  const currentConfig = ref(null);
  const submitting = ref(false);
  const targetLoading = ref(false);
  const targetOptions = ref([]);
  const formRef = ref(null);

  const form = reactive(emptyConversionDeductionForm());
  const rules = createConversionDeductionFormRules(() => form);

  const volumeRatioPercent = computed({
    get: () => form.volume_deduction_ratio * 100,
    set: (val) => {
      form.volume_deduction_ratio = val / 100;
    },
  });

  const amountRatioPercent = computed({
    get: () => form.amount_deduction_ratio * 100,
    set: (val) => {
      form.amount_deduction_ratio = val / 100;
    },
  });

  const resetForm = () => {
    Object.assign(form, emptyConversionDeductionForm());
    targetOptions.value = [];
    formRef.value?.clearValidate();
  };

  const handleLevelChange = async (level) => {
    form.target_id = null;
    targetOptions.value = [];
    if (!level) return;

    targetLoading.value = true;
    try {
      let allItems = [];
      let page = 1;
      const pageSize = 100;
      let hasMore = true;

      while (hasMore) {
        let response;
        if (level === 'advertiser') {
          response = await getAdvertisers({ page, page_size: pageSize });
        } else if (level === 'offer') {
          response = await getOffers({ page, page_size: pageSize });
        } else if (level === 'publisher') {
          response = await getPublishers({ page, page_size: pageSize });
        } else {
          break;
        }

        const items = response.data || [];
        allItems = allItems.concat(items);
        const total = response.total || 0;
        hasMore = allItems.length < total && items.length > 0;
        page += 1;
      }

      const sortedItems =
        level === 'offer' ? allItems.slice().sort((a, b) => a.id - b.id) : allItems;
      targetOptions.value = sortedItems.map((item) => ({
        id: item.id,
        name:
          level === 'offer'
            ? `${item.id} - ${item.offer_name}`
            : item.advertiser_name || item.offer_name || item.publisher_name,
      }));
    } catch (error) {
      logger.error('加载配置对象列表失败:', error);
      ElMessage.error(`加载配置对象列表失败：${error.message || '未知错误'}`);
    } finally {
      targetLoading.value = false;
    }
  };

  const handleAdd = async () => {
    try {
      await getDeductionConfigs({ page: 1, page_size: 1 });
    } catch (error) {
      logger.debug('获取CSRF令牌失败，但可能已从响应头获取:', error);
    }
    dialogMode.value = 'add';
    currentConfig.value = null;
    resetForm();
    dialogVisible.value = true;
  };

  const fillFormFromRow = (row, defaultActive = row.is_active) => {
    Object.assign(form, {
      level: row.level,
      target_id: row.target_id,
      enable_volume_deduction: row.enable_volume_deduction,
      volume_deduction_ratio: row.volume_deduction_ratio,
      deduction_strategy: row.deduction_strategy,
      enable_amount_deduction: row.enable_amount_deduction,
      amount_deduction_ratio: row.amount_deduction_ratio,
      priority: row.priority,
      is_active: defaultActive,
    });
    handleLevelChange(row.level);
  };

  const handleEdit = (row) => {
    dialogMode.value = 'edit';
    currentConfig.value = { ...row };
    fillFormFromRow(row);
    dialogVisible.value = true;
  };

  const handleCopy = (row) => {
    dialogMode.value = 'add';
    currentConfig.value = null;
    fillFormFromRow(row, false);
    dialogVisible.value = true;
    ElMessage.info('已复制配置，请检查并修改后保存（默认状态为禁用）');
  };

  const handleDialogClose = () => {
    dialogVisible.value = false;
    resetForm();
  };

  const handleSubmit = async () => {
    if (!formRef.value) return;

    await formRef.value.validate(async (valid) => {
      if (!valid) return;

      if (!form.enable_volume_deduction && !form.enable_amount_deduction) {
        ElMessage.warning('请至少启用一种扣减方式（扣量或扣金额）');
        return;
      }

      submitting.value = true;
      try {
        const data = {
          level: form.level,
          target_id: form.target_id,
          enable_volume_deduction: form.enable_volume_deduction,
          volume_deduction_ratio: form.enable_volume_deduction
            ? form.volume_deduction_ratio
            : 0,
          deduction_strategy: form.enable_volume_deduction
            ? form.deduction_strategy
            : 'random',
          enable_amount_deduction: form.enable_amount_deduction,
          amount_deduction_ratio: form.enable_amount_deduction
            ? form.amount_deduction_ratio
            : 0,
          priority: form.priority,
          is_active: form.is_active,
        };

        if (dialogMode.value === 'add') {
          await createDeductionConfig(data);
          ElMessage.success('添加成功');
        } else {
          await updateDeductionConfig(currentConfig.value.id, data);
          ElMessage.success('更新成功');
        }

        dialogVisible.value = false;
        await fetchData();
      } catch (error) {
        logger.error('提交扣减配置失败:', error);
        const errorMsg =
          error.response?.data?.detail ||
          error.response?.data?.message ||
          error.message ||
          '未知错误';
        ElMessage.error(
          `${dialogMode.value === 'add' ? '添加' : '更新'}失败：${errorMsg}`,
        );
      } finally {
        submitting.value = false;
      }
    });
  };

  watch(dialogVisible, (val) => {
    if (val && dialogMode.value === 'add' && !form.target_id) {
      handleLevelChange(form.level || 'advertiser');
    }
  });

  return {
    dialogVisible,
    dialogMode,
    submitting,
    targetLoading,
    targetOptions,
    formRef,
    form,
    rules,
    volumeRatioPercent,
    amountRatioPercent,
    handleLevelChange,
    handleAdd,
    handleEdit,
    handleCopy,
    handleDialogClose,
    handleSubmit,
  };
}
