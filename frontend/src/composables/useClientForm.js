import { ref, reactive } from 'vue';

/**
 * 客户表单管理 Composable
 * 处理表单状态和对话框
 */
export function useClientForm() {
  const dialogVisible = ref(false);
  const dialogTitle = ref('添加客户');
  const currentClientId = ref(null);
  const clientFormDialogRef = ref(null);

  // 客户表单数据
  const clientForm = reactive({
    username: '',
    password: '',
    email: '',
    full_name: '',
    key: '',  // 客户API密钥UUID
    company_name: '',
    contact_person: '',
    phone: '',
    address: '',
    is_active: true
  });

  /**
   * 重置表单数据
   */
  const resetForm = () => {
    Object.assign(clientForm, {
      username: '',
      password: '',
      email: '',
      full_name: '',
      key: '',
      company_name: '',
      contact_person: '',
      phone: '',
      address: '',
      is_active: true
    });
    currentClientId.value = null;
  };

  /**
   * 打开添加对话框
   */
  const openAddDialog = () => {
    currentClientId.value = null;
    dialogTitle.value = '添加客户';
    resetForm();
    dialogVisible.value = true;
  };

  /**
   * 打开编辑对话框
   * @param {Object} clientData - 客户数据
   */
  const openEditDialog = (clientData) => {
    currentClientId.value = clientData.id;
    dialogTitle.value = '编辑客户';
    Object.assign(clientForm, {
      key: clientData.key || '',
      company_name: clientData.company_name || '',
      contact_person: clientData.contact_person || '',
      phone: clientData.phone || '',
      address: clientData.address || '',
      is_active: clientData.is_active !== undefined ? clientData.is_active : true
    });
    dialogVisible.value = true;
  };

  /**
   * 关闭对话框
   */
  const closeDialog = () => {
    resetForm();
    dialogVisible.value = false;
  };

  return {
    dialogVisible,
    dialogTitle,
    currentClientId,
    clientFormDialogRef,
    clientForm,
    resetForm,
    openAddDialog,
    openEditDialog,
    closeDialog
  };
}

