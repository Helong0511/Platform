import { reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  getOffers,
  createOffer,
  updateOffer,
  deleteOffer,
  getOffer,
  checkOfferShortLink,
} from '../api/offer';
import { ensureCsrfToken } from '../utils/csrfMutate';
import { logger } from '../utils/logger';
import { createOfferTracklinkRules } from '../utils/shortLinkFormRules';

export function createEmptyOfferForm() {
  return {
    offer_name: '',
    advertiser_id: null,
    advertiser_offer_id: '',
    preview_link: '',
    payout: null,
    affiliate_payout: null,
    country: '',
    category: '',
    type: '',
    status: 'Active',
    upstream_cap: null,
    downstream_cap: null,
    advertiser_tracklink: '',
    downstream_tracklink: '',
    downstream_tracklink_short: '',
    postback_url: '',
    postback_method: 'GET',
    click_validity_hours: 720,
    publisher_configs: [{ publisher_id: null, affiliate_payout: null, downstream_cap: null }],
    is_active: true,
  };
}

function publisherConfigsFromOffer(offerData) {
  if (offerData.assigned_publishers?.length) {
    return offerData.assigned_publishers.map((p) => ({
      publisher_id: p.id,
      affiliate_payout: p.affiliate_payout ?? null,
      downstream_cap: p.downstream_cap ?? null,
    }));
  }
  return [{ publisher_id: null, affiliate_payout: null, downstream_cap: null }];
}

function mapOfferToForm(offerData) {
  return {
    id: offerData.id,
    offer_name: offerData.offer_name,
    advertiser_id: offerData.advertiser_id,
    advertiser_offer_id: offerData.advertiser_offer_id || '',
    preview_link: offerData.preview_link || '',
    payout: offerData.payout,
    affiliate_payout: offerData.affiliate_payout,
    country: offerData.country || '',
    category: offerData.category || '',
    type: offerData.type || '',
    status: offerData.status,
    upstream_cap: offerData.upstream_cap,
    downstream_cap: offerData.downstream_cap,
    advertiser_tracklink: offerData.advertiser_tracklink || '',
    downstream_tracklink: offerData.downstream_tracklink || '',
    downstream_tracklink_short: '',
    postback_url: offerData.postback_url || '',
    postback_method: offerData.postback_method || 'GET',
    click_validity_hours: offerData.click_validity_hours || 720,
    publisher_configs: publisherConfigsFromOffer(offerData),
    is_active: offerData.is_active,
  };
}

/**
 * Offer 创建/编辑表单与行内开关、删除。
 */
export function useOfferForm({ isAdmin, loadData, publisherList }) {
  const submitting = ref(false);
  const dialogVisible = ref(false);
  const isEdit = ref(false);
  const formRef = ref(null);
  const generatingShortLink = ref(false);
  const shortLinkExists = ref(false);
  const formData = reactive(createEmptyOfferForm());

  const formRules = {
    offer_name: [{ required: true, message: '请输入Offer名称', trigger: 'blur' }],
    advertiser_id: [{ required: true, message: '请选择广告主', trigger: 'change' }],
    ...createOfferTracklinkRules(() => formData),
    'publisher_configs.*.downstream_cap': [
      { type: 'number', min: 0, message: '下游Cap不能为负数', trigger: 'blur' },
    ],
    'publisher_configs.*.affiliate_payout': [
      { type: 'number', min: 0, message: '下游PO不能为负数', trigger: 'blur' },
    ],
  };

  const addPublisherConfig = () => {
    formData.publisher_configs.push({
      publisher_id: null,
      affiliate_payout: null,
      downstream_cap: null,
    });
  };

  const removePublisherConfig = (index) => {
    formData.publisher_configs.splice(index, 1);
  };

  const isPublisherSelected = (publisherId, currentIndex) => {
    if (!publisherId) return false;
    return formData.publisher_configs.some(
      (config, index) => index !== currentIndex && config.publisher_id === publisherId,
    );
  };

  const getPublisherName = (publisherId) => {
    if (!publisherId) return '';
    const publisher = publisherList.value.find((p) => p.id === publisherId);
    return publisher ? publisher.publisher_name : '';
  };

  const ensureCsrfForOffer = async () => {
    const hasToken = await ensureCsrfToken(() => getOffers({ page: 1, page_size: 1 }));
    if (!hasToken) {
      ElMessage.warning('无法获取CSRF令牌，请刷新页面后重试');
      return false;
    }
    return true;
  };

  const checkExistingShortLink = async (offerId) => {
    if (!offerId || !isEdit.value) {
      shortLinkExists.value = false;
      return;
    }
    try {
      const result = await checkOfferShortLink(offerId);
      if (result) {
        shortLinkExists.value = result.exists;
        formData.downstream_tracklink_short =
          result.exists && result.short_link ? result.short_link.short_url : '';
      } else {
        shortLinkExists.value = false;
        formData.downstream_tracklink_short = '';
      }
    } catch (error) {
      logger.error('检查短链接失败:', error);
      shortLinkExists.value = false;
      formData.downstream_tracklink_short = '';
    }
  };

  const handleAdd = async () => {
    try {
      if (!(await ensureCsrfForOffer())) return;
    } catch (error) {
      if (error.response?.status === 401) return;
      logger.error('获取CSRF令牌失败:', error);
      ElMessage.warning('CSRF令牌获取失败，请刷新页面后重试');
      return;
    }
    isEdit.value = false;
    Object.assign(formData, createEmptyOfferForm());
    dialogVisible.value = true;
  };

  const handleEdit = async (row) => {
    isEdit.value = true;
    try {
      const offerData = await getOffer(row.id);
      if (offerData) {
        Object.assign(formData, mapOfferToForm(offerData));
        if (isAdmin.value && offerData.id) {
          await checkExistingShortLink(offerData.id);
        }
      } else {
        Object.assign(formData, mapOfferToForm(row));
        if (isAdmin.value && row.id) {
          await checkExistingShortLink(row.id);
        }
      }
    } catch (error) {
      logger.error('获取Offer详情失败:', error);
      ElMessage.error('获取Offer详情失败');
      return;
    }
    dialogVisible.value = true;
  };

  const handleDelete = async (row) => {
    try {
      await ElMessageBox.confirm(`确定要删除Offer "${row.offer_name}" 吗？`, '确认删除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      });
      await deleteOffer(row.id);
      ElMessage.success('删除成功');
      loadData();
    } catch (error) {
      if (error === 'cancel') return;
      logger.error('删除Offer失败:', error);
      if (error.response?.status === 401) return;
      if (error.response?.status === 403 && error._handled) return;
      const errorMsg =
        error.response?.data?.detail ||
        error.response?.data?.message ||
        error.message ||
        '删除失败';
      ElMessage.error(errorMsg);
    }
  };

  const handleToggleActive = async (row) => {
    const originalState = row.is_active;
    try {
      row.is_active = !row.is_active;
      await updateOffer(row.id, { is_active: row.is_active });
      ElMessage.success(row.is_active ? '已激活' : '已停用');
      loadData();
    } catch (error) {
      row.is_active = originalState;
      if (error.response?.status === 401) return;
      if (error.response?.status === 403 && error._handled) return;
      ElMessage.error(error.response?.data?.detail || error.message || '更新失败');
    }
  };

  const handleToggleStatus = async (row, value) => {
    const originalStatus = row.status;
    try {
      row.status = value;
      await updateOffer(row.id, { status: value });
      ElMessage.success('状态更新成功');
      loadData();
    } catch (error) {
      row.status = originalStatus;
      if (error.response?.status === 401) return;
      if (error.response?.status === 403 && error._handled) return;
      ElMessage.error(error.response?.data?.detail || error.message || '更新失败');
    }
  };

  const handleSubmit = async () => {
    if (!formRef.value) return;
    await formRef.value.validate(async (valid) => {
      if (!valid) return;
      const validConfigs = formData.publisher_configs.filter((c) => c.publisher_id !== null);
      if (validConfigs.length === 0) {
        ElMessage.warning('请至少添加一个渠道配置');
        return;
      }
      const publisherIds = validConfigs.map((c) => c.publisher_id);
      if (publisherIds.length !== new Set(publisherIds).size) {
        ElMessage.warning('渠道配置中存在重复的渠道，请检查');
        return;
      }
      submitting.value = true;
      try {
        try {
          if (!(await ensureCsrfToken(() => getOffers({ page: 1, page_size: 1 })))) {
            ElMessage.warning('CSRF令牌已过期，请刷新页面后重试');
            return;
          }
        } catch (csrfError) {
          if (csrfError.response?.status === 401) return;
          ElMessage.warning('CSRF令牌验证失败，请刷新页面后重试');
          return;
        }
        const submitData = { ...formData };
        submitData.publisher_configs = validConfigs;
        delete submitData.postback_url;
        delete submitData.postback_method;
        let offerData;
        if (isEdit.value) {
          offerData = await updateOffer(formData.id, submitData);
        } else {
          offerData = await createOffer(submitData);
        }
        ElMessage.success(isEdit.value ? '更新成功' : '创建成功');
        if (offerData?.downstream_tracklink) {
          formData.downstream_tracklink = offerData.downstream_tracklink;
          formData.downstream_tracklink_short = offerData.downstream_tracklink;
        }
        if (isEdit.value && isAdmin.value && offerData?.id) {
          await checkExistingShortLink(offerData.id);
        }
        dialogVisible.value = false;
        loadData();
      } catch (error) {
        logger.error('提交失败:', error);
        if (error.response?.status === 401) return;
        if (error.response?.status === 403 && error._handled) return;
        ElMessage.error(
          error.response?.data?.detail || error.response?.data?.message || error.message || '操作失败',
        );
      } finally {
        submitting.value = false;
      }
    });
  };

  const handleDialogClose = () => {
    formRef.value?.resetFields();
    formData.downstream_tracklink_short = '';
    shortLinkExists.value = false;
  };

  const generateShortLinkForOffer = async () => {
    if (!formData.advertiser_tracklink) {
      ElMessage.warning('请先配置上游Tracklink');
      return;
    }
    if (!isEdit.value) {
      ElMessage.info('新建Offer需要先保存才能生成短链接（保存时会根据分配的渠道自动生成）');
      return;
    }
    generatingShortLink.value = true;
    try {
      await checkExistingShortLink(formData.id);
      if (shortLinkExists.value) {
        ElMessage.success('短链接已存在');
      } else {
        ElMessage.info('保存Offer时会自动创建短链接（使用上游Tracklink作为原始URL）');
      }
    } catch (error) {
      if (error.response?.status === 401 || (error.response?.status === 403 && error._handled)) {
        return;
      }
      ElMessage.error(
        error.response?.data?.detail || error.response?.data?.message || error.message || '操作失败',
      );
    } finally {
      generatingShortLink.value = false;
    }
  };

  return {
    submitting,
    dialogVisible,
    isEdit,
    formRef,
    formData,
    formRules,
    generatingShortLink,
    shortLinkExists,
    addPublisherConfig,
    removePublisherConfig,
    isPublisherSelected,
    getPublisherName,
    handleAdd,
    handleEdit,
    handleDelete,
    handleToggleActive,
    handleToggleStatus,
    handleSubmit,
    handleDialogClose,
    generateShortLinkForOffer,
    checkExistingShortLink,
  };
}
