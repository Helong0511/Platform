import { reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getCaps, createCap, updateCap, deleteCap } from '../api/cap';
import { logger } from '../utils/logger';
import { createCapFormRules } from '../utils/capFormRules';

const emptyForm = () => ({
  cap_type: 'offer',
  advertiser_id: null,
  offer_id: null,
  publisher_id: null,
  daily_cap: null,
  total_cap: null,
  is_active: true,
});

/**
 * Cap 配置创建/编辑对话框。
 * @param {{ loadData: () => Promise<void> }} deps
 */
export function useCapForm({ loadData }) {
  const submitting = ref(false);
  const dialogVisible = ref(false);
  const isEdit = ref(false);
  const formRef = ref(null);
  const formData = reactive(emptyForm());
  const formRules = createCapFormRules(() => formData);

  const handleCapTypeChange = () => {
    if (formData.cap_type !== 'advertiser_offer') {
      formData.advertiser_id = null;
    }
  };

  const handleAdd = async () => {
    try {
      await getCaps({ page: 1, page_size: 1 });
    } catch (error) {
      logger.debug('获取CSRF令牌失败，但可能已从响应头获取:', error);
    }
    isEdit.value = false;
    Object.assign(formData, emptyForm());
    dialogVisible.value = true;
  };

  const handleEdit = (row) => {
    isEdit.value = true;
    Object.assign(formData, {
      id: row.id,
      cap_type: row.cap_type,
      advertiser_id: row.advertiser_id,
      offer_id: row.offer_id,
      publisher_id: row.publisher_id,
      daily_cap: row.daily_cap,
      total_cap: row.total_cap,
      is_active: row.is_active,
    });
    dialogVisible.value = true;
  };

  const handleDelete = async (row) => {
    try {
      await ElMessageBox.confirm('确定要删除此Cap配置吗？', '确认删除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      });
      await deleteCap(row.id);
      ElMessage.success('删除成功');
      loadData();
    } catch (error) {
      if (error !== 'cancel') {
        logger.error('删除Cap配置失败:', error);
        ElMessage.error('删除失败');
      }
    }
  };

  const handleSubmit = async () => {
    if (!formRef.value) return;
    await formRef.value.validate(async (valid) => {
      if (!valid) return;
      submitting.value = true;
      try {
        if (isEdit.value) {
          await updateCap(formData.id, formData);
        } else {
          await createCap(formData);
        }
        ElMessage.success(isEdit.value ? '更新成功' : '创建成功');
        dialogVisible.value = false;
        loadData();
      } catch (error) {
        logger.error('提交失败:', error);
        if (error.response?.status === 401) return;
        if (error.response?.status === 403 && error._handled) return;
        const errorMsg =
          error.response?.data?.detail ||
          error.response?.data?.message ||
          error.message ||
          '操作失败';
        ElMessage.error(errorMsg);
      } finally {
        submitting.value = false;
      }
    });
  };

  const handleDialogClose = () => {
    formRef.value?.resetFields();
  };

  return {
    submitting,
    dialogVisible,
    isEdit,
    formRef,
    formData,
    formRules,
    handleCapTypeChange,
    handleAdd,
    handleEdit,
    handleDelete,
    handleSubmit,
    handleDialogClose,
  };
}
