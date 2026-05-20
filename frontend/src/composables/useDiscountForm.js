import { reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getDiscounts, createDiscount, updateDiscount, deleteDiscount } from '../api/discount';
import { logger } from '../utils/logger';
import { createDiscountFormRules } from '../utils/discountFormRules';

const emptyForm = () => ({
  discount_type: 'offer',
  offer_id: null,
  publisher_id: null,
  discount_ratio: 0,
  is_active: true,
});

/**
 * 扣量配置创建/编辑对话框。
 * @param {{ loadData: () => Promise<void> }} deps
 */
export function useDiscountForm({ loadData }) {
  const submitting = ref(false);
  const dialogVisible = ref(false);
  const isEdit = ref(false);
  const formRef = ref(null);
  const formData = reactive(emptyForm());
  const formRules = createDiscountFormRules(() => formData);

  const handleDiscountTypeChange = () => {
    if (formData.discount_type !== 'offer') {
      formData.offer_id = null;
    }
  };

  const handleAdd = async () => {
    try {
      await getDiscounts({ page: 1, page_size: 1 });
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
      discount_type: row.discount_type,
      offer_id: row.offer_id,
      publisher_id: row.publisher_id,
      discount_ratio: row.discount_ratio,
      is_active: row.is_active,
    });
    dialogVisible.value = true;
  };

  const handleDelete = async (row) => {
    try {
      await ElMessageBox.confirm('确定要删除此扣量配置吗？', '确认删除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      });
      await deleteDiscount(row.id);
      ElMessage.success('删除成功');
      loadData();
    } catch (error) {
      if (error !== 'cancel') {
        logger.error('删除扣量配置失败:', error);
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
          await updateDiscount(formData.id, formData);
        } else {
          await createDiscount(formData);
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
    handleDiscountTypeChange,
    handleAdd,
    handleEdit,
    handleDelete,
    handleSubmit,
    handleDialogClose,
  };
}
