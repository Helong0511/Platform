import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getClientList, getClientDetail, createClient, updateClient, deleteClient } from '../api/client';
import { extractErrorMessage, isErrorHandled } from '../utils/api';
import { ensureCsrfToken } from '../utils/csrfMutate';

/**
 * 客户管理 Composable
 * 处理客户的CRUD操作
 */
export function useClients() {
  const clients = ref([]);
  const loading = ref(false);
  const saving = ref(false);

  /**
   * 获取客户列表
   * @param {Object} params - 查询参数
   * @returns {Promise<Object>} 返回客户列表和总数
   */
  const fetchClients = async (params = {}) => {
    try {
      loading.value = true;
      const response = await getClientList(params);

      // response已经是标准分页格式，直接使用data和total字段
      // getClientList使用paginated: true，失败时会抛出异常
      clients.value = response.data || [];
      return {
        data: response.data || [],
        total: response.total || 0
      };
    } catch (error) {
      if (!isErrorHandled(error)) {
        const errorMsg = extractErrorMessage(error);
        ElMessage.error(errorMsg);
      }
      clients.value = [];
      return { data: [], total: 0 };
    } finally {
      loading.value = false;
    }
  };

  /**
   * 获取客户详情
   * @param {number} id - 客户ID
   * @returns {Promise<Object|null>} 客户详情数据
   */
  const fetchClientDetail = async (id) => {
    try {
      loading.value = true;
      // getClientDetail使用returnDataOnly: true，直接返回数据对象（可能来自缓存或API）
      const data = await getClientDetail(id);
      return data || null;
    } catch (error) {
      if (!isErrorHandled(error)) {
        const errorMsg = extractErrorMessage(error);
        ElMessage.error(errorMsg);
      }
      return null;
    } finally {
      loading.value = false;
    }
  };

  /**
   * 保存客户（创建或更新）
   * @param {number|null} clientId - 客户ID，null表示创建
   * @param {Object} formData - 表单数据
   * @returns {Promise<boolean>} 是否保存成功
   */
  const saveClient = async (clientId, formData) => {
    try {
      saving.value = true;

      // 准备提交数据
      const submitData = {
        company_name: formData.company_name.trim(),
        contact_person: formData.contact_person?.trim() || null,
        phone: formData.phone?.trim() || null,
        address: formData.address?.trim() || null,
        is_active: formData.is_active !== undefined ? formData.is_active : true
      };

      let response;
      if (!clientId) {
        // 创建客户：提供用户信息
        submitData.username = formData.username.trim();
        submitData.password = formData.password;
        submitData.email = formData.email.trim();
        if (formData.full_name) {
          submitData.full_name = formData.full_name.trim();
        }
        response = await createClient(submitData);
      } else {
        // 更新客户
        response = await updateClient(clientId, submitData);
      }

      // createClient和updateClient使用returnDataOnly: true，成功时直接返回数据，失败时抛出异常
      // 如果执行到这里，说明操作成功（失败会抛出异常）
      ElMessage.success(clientId ? '客户更新成功' : '客户创建成功');
      return true;
    } catch (error) {
      if (!error.message?.includes('取消') && !error.message?.includes('validate')) {
        if (!isErrorHandled(error)) {
          const errorMsg = extractErrorMessage(error);
          ElMessage.error(errorMsg);
        }
      }
      return false;
    } finally {
      saving.value = false;
    }
  };

  /**
   * 删除客户
   * @param {number} id - 客户ID
   * @returns {Promise<boolean>} 是否删除成功
   */
  const removeClient = async (id) => {
    try {
      await ElMessageBox.confirm(
        '确定要删除此客户吗？此操作不可撤销，且会删除关联的产品数据。',
        '确认删除',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning',
          appendTo: document.body, // 确保弹窗附加到 body，避免被对话框遮挡
          zIndex: 3001 // 确保 z-index 高于对话框
        }
      );

      // 确保CSRF令牌存在
      await ensureCsrfToken(() => fetchClients());
      
      loading.value = true;
      await deleteClient(id);
      ElMessage.success('客户删除成功');
      return true;
    } catch (error) {
      if (!error.message?.includes('取消')) {
        if (!isErrorHandled(error)) {
          const errorMsg = extractErrorMessage(error);
          ElMessage.error(errorMsg);
        }
      }
      return false;
    } finally {
      loading.value = false;
    }
  };

  return {
    clients,
    loading,
    saving,
    fetchClients,
    fetchClientDetail,
    saveClient,
    removeClient
  };
}

