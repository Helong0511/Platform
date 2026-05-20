import { reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  createShortLink,
  updateShortLink,
  deleteShortLink,
  generateShortCode,
} from '../api/short-link';
import { logger } from '../utils/logger';
import { shortLinkFormRules } from '../utils/shortLinkFormRules';

const emptyForm = () => ({
  original_url: '',
  short_code: '',
  title: '',
  description: '',
  offer_id: null,
  channel_id: null,
  expires_at: null,
  is_active: true,
});

/**
 * 短链接创建/编辑对话框与保存、删除。
 * @param {{ refreshListAndStats: () => Promise<void> }} deps
 */
export function useShortLinkForm({ refreshListAndStats }) {
  const saving = ref(false);
  const generatingCode = ref(false);
  const dialogVisible = ref(false);
  const isEdit = ref(false);
  const currentLinkId = ref(null);
  const formData = reactive(emptyForm());

  const handleCreate = () => {
    isEdit.value = false;
    currentLinkId.value = null;
    Object.assign(formData, emptyForm());
    dialogVisible.value = true;
  };

  const handleEdit = (link) => {
    isEdit.value = true;
    currentLinkId.value = link.id;
    Object.assign(formData, {
      original_url: link.original_url,
      short_code: link.short_code,
      title: link.title || '',
      description: link.description || '',
      offer_id: link.offer_id || null,
      channel_id: link.channel_id || null,
      expires_at: link.expires_at || null,
      is_active: link.is_active,
    });
    dialogVisible.value = true;
  };

  const handleSave = async () => {
    try {
      saving.value = true;
      const submitData = { ...formData };
      if (!submitData.short_code) {
        delete submitData.short_code;
      }
      if (isEdit.value) {
        await updateShortLink(currentLinkId.value, submitData);
        ElMessage.success('短链接更新成功');
      } else {
        await createShortLink(submitData);
        ElMessage.success('短链接创建成功');
      }
      dialogVisible.value = false;
      await refreshListAndStats();
    } catch (error) {
      logger.error('保存短链接失败:', error);
      const errorMessage =
        error.response?.data?.detail ||
        error.response?.data?.message ||
        error.message ||
        '保存失败，请稍后重试';
      ElMessage.error(errorMessage);
    } finally {
      saving.value = false;
    }
  };

  const handleDelete = async (linkId) => {
    try {
      await ElMessageBox.confirm('确定要删除这个短链接吗？', '确认删除', {
        type: 'warning',
      });
      await deleteShortLink(linkId);
      ElMessage.success('短链接已删除');
      await refreshListAndStats();
    } catch (error) {
      if (error !== 'cancel') {
        logger.error('删除短链接失败:', error);
      }
    }
  };

  const handleGenerateCode = async () => {
    if (isEdit.value) return;
    generatingCode.value = true;
    try {
      const result = await generateShortCode();
      if (result?.short_code) {
        formData.short_code = result.short_code;
        ElMessage.success('代码已生成');
      }
    } catch (error) {
      logger.error('生成代码失败:', error);
    } finally {
      generatingCode.value = false;
    }
  };

  const handleDialogClose = () => {
    dialogVisible.value = false;
  };

  return {
    saving,
    generatingCode,
    dialogVisible,
    isEdit,
    formData,
    formRules: shortLinkFormRules,
    handleCreate,
    handleEdit,
    handleSave,
    handleDelete,
    handleGenerateCode,
    handleDialogClose,
  };
}
