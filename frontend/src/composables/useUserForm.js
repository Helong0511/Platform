import { computed, nextTick, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import {
  createUser,
  updateUser,
  getUserDetail,
} from '../api/user';
import { updateClient, createClient } from '../api/client';
import { extractErrorMessage, isErrorHandled } from '../utils/api';
import { ensureCsrfToken } from '../utils/csrfMutate';
import { formatDate } from '../utils/dateFormat';
import { generateUUID } from '../utils/uuid';
import { logger } from '../utils/logger';

export function createEmptyUserForm() {
  return {
    username: '',
    email: '',
    password: '',
    full_name: '',
    role: 'client',
    is_active: true,
    company_name: '',
    contact_person: '',
    phone: '',
    address: '',
    client_id: null,
    client_key: '',
    isKeyEditable: false,
  };
}

function mapUserToForm(userData, fallbackUser) {
  const formData = {
    username: userData.username || '',
    email: userData.email || '',
    full_name: userData.full_name || '',
    role: userData.role || 'client',
    is_active: userData.is_active !== undefined ? userData.is_active : true,
    password: '',
    company_name: '',
    contact_person: '',
    phone: '',
    address: '',
    client_id: null,
    client_key: '',
    isKeyEditable: false,
  };
  const client =
    userData.role === 'client'
      ? userData.client || fallbackUser?.client
      : null;
  if (client) {
    formData.company_name = client.company_name || '';
    formData.contact_person = client.contact_person || '';
    formData.phone = client.phone || '';
    formData.address = client.address || '';
    formData.client_id = client.id || null;
    formData.client_key = client.key || '';
  }
  return formData;
}

/**
 * 用户添加/编辑/查看表单。
 */
export function useUserForm({ users, loading, fetchUsers, fetchStats }) {
  const dialogVisible = ref(false);
  const viewDialogVisible = ref(false);
  const dialogTitle = ref('添加用户');
  const currentUserId = ref(null);
  const viewingUser = ref(null);
  const userFormRef = ref(null);
  const userForm = reactive(createEmptyUserForm());

  const showClientForm = computed(() => {
    if (userForm.role === 'client') {
      return true;
    }
    if (currentUserId.value) {
      const editingUser = users.value.find((u) => u.id === currentUserId.value);
      return editingUser?.role === 'client';
    }
    return false;
  });

  const formRules = computed(() => {
    const rules = {
      username: [
        { required: true, message: '请输入登录名（用户名）', trigger: 'blur' },
        { min: 3, max: 20, message: '用户名长度在 3 到 20 个字符', trigger: 'blur' },
        { pattern: /^[a-zA-Z0-9_]+$/, message: '用户名只能包含字母、数字和下划线', trigger: 'blur' },
      ],
      full_name: [{ required: true, message: '请输入全名', trigger: 'blur' }],
      email: [
        { required: true, message: '请输入邮箱', trigger: 'blur' },
        { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' },
      ],
      role: [{ required: true, message: '请选择角色', trigger: 'change' }],
    };
    if (!currentUserId.value) {
      rules.password = [
        { required: true, message: '请输入密码', trigger: 'blur' },
        { min: 6, message: '密码长度不能少于 6 个字符', trigger: 'blur' },
        { max: 72, message: '密码长度不能超过 72 个字符（bcrypt算法限制）', trigger: 'blur' },
      ];
    } else {
      rules.password = [
        { max: 72, message: '密码长度不能超过 72 个字符（bcrypt算法限制）', trigger: 'blur' },
      ];
    }
    if (!currentUserId.value && userForm.role === 'client') {
      rules.company_name = [{ required: true, message: '请输入公司名称', trigger: 'blur' }];
    } else if (!rules.company_name) {
      rules.company_name = [];
    }
    return rules;
  });

  const handleUsernameBlur = () => {
    if (!currentUserId.value && userForm.username?.trim()) {
      const username = userForm.username.trim();
      if (!userForm.full_name?.trim()) userForm.full_name = username;
      if (!userForm.email?.trim()) userForm.email = `${username}@btfrx.online`;
      if (!userForm.password?.trim()) userForm.password = `${username}123456`;
      if (userForm.role === 'client' && !userForm.company_name?.trim()) {
        userForm.company_name = username;
      }
    }
  };

  const handleRoleChange = () => {
    if (userForm.role !== 'client') {
      userForm.company_name = '';
      userForm.contact_person = '';
      userForm.phone = '';
      userForm.address = '';
      userForm.client_id = null;
    } else if (
      !currentUserId.value &&
      userForm.username?.trim() &&
      !userForm.company_name?.trim()
    ) {
      userForm.company_name = userForm.username.trim();
    }
  };

  const handleAddUser = () => {
    currentUserId.value = null;
    dialogTitle.value = '添加用户';
    Object.assign(userForm, createEmptyUserForm());
    dialogVisible.value = true;
    nextTick(() => userFormRef.value?.clearValidate());
  };

  const handleView = async (user) => {
    try {
      viewingUser.value = await getUserDetail(user.id);
      viewDialogVisible.value = true;
    } catch (error) {
      logger.error('获取用户详情失败:', error);
      if (!isErrorHandled(error)) {
        ElMessage.warning('获取用户详情失败，使用列表数据');
      }
      viewingUser.value = user;
      viewDialogVisible.value = true;
    }
  };

  const handleKeyDoubleClick = (event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    userForm.client_key = generateUUID();
    userForm.isKeyEditable = true;
    ElMessage.success('已自动生成新的UUID，您可以继续编辑或直接保存');
  };

  const handleEdit = async (user) => {
    currentUserId.value = user.id;
    dialogTitle.value = user.role === 'admin' ? '编辑管理员' : '编辑客户';
    try {
      const userData = await getUserDetail(user.id);
      Object.assign(userForm, mapUserToForm(userData, user));
      userForm.isKeyEditable = false;
    } catch (error) {
      logger.error('获取用户详情失败:', error);
      if (!isErrorHandled(error)) {
        ElMessage.warning('获取用户详情失败，使用列表数据');
      }
      Object.assign(userForm, mapUserToForm(user, user));
    }
    userFormRef.value?.clearValidate();
    dialogVisible.value = true;
  };

  const handleSaveUser = async () => {
    if (!userFormRef.value) {
      ElMessage.warning('表单未初始化，请稍后再试');
      return;
    }
    try {
      await ensureCsrfToken(() => fetchUsers());
      if (!currentUserId.value && userForm.username?.trim()) {
        handleUsernameBlur();
      }
      await userFormRef.value.validate();
      loading.value = true;

      const submitData = {
        username: userForm.username.trim(),
        email: userForm.email.trim(),
        full_name: userForm.full_name?.trim() || null,
        role: userForm.role,
        is_active: userForm.is_active,
      };
      if (userForm.password?.trim()) {
        submitData.password = userForm.password;
      } else if (!currentUserId.value) {
        ElMessage.error('请输入密码');
        loading.value = false;
        return;
      }
      if (!currentUserId.value && userForm.role === 'client') {
        submitData.company_name = userForm.company_name?.trim() || null;
        submitData.contact_person = userForm.contact_person?.trim() || null;
        submitData.phone = userForm.phone?.trim() || null;
        submitData.address = userForm.address?.trim() || null;
      }

      if (currentUserId.value) {
        const updateData = { ...submitData };
        if (!updateData.password) delete updateData.password;
        await updateUser(currentUserId.value, updateData);
        if (userForm.role === 'client') {
          await ensureCsrfToken(() => fetchUsers());
          if (userForm.client_id) {
            const clientUpdate = {
              company_name: userForm.company_name.trim(),
              contact_person: userForm.contact_person?.trim() || null,
              phone: userForm.phone?.trim() || null,
              address: userForm.address?.trim() || null,
              is_active: userForm.is_active,
            };
            if (userForm.isKeyEditable && userForm.client_key) {
              clientUpdate.key = userForm.client_key.trim();
            }
            await updateClient(userForm.client_id, clientUpdate);
          } else if (userForm.company_name) {
            const response = await createClient({
              user_id: currentUserId.value,
              company_name: userForm.company_name.trim(),
              contact_person: userForm.contact_person?.trim() || null,
              phone: userForm.phone?.trim() || null,
              address: userForm.address?.trim() || null,
              is_active: userForm.is_active !== undefined ? userForm.is_active : true,
            });
            if (response?.data?.id) {
              userForm.client_id = response.data.id;
            }
            ElMessage.success('客户信息创建成功');
          }
        }
      } else {
        await createUser(submitData);
      }

      dialogVisible.value = false;
      await fetchUsers(true);
      await new Promise((r) => setTimeout(r, 200));
      await fetchStats();
      ElMessage.success(currentUserId.value ? '用户更新成功' : '用户创建成功');
    } catch (error) {
      if (!error.message?.includes('取消') && !isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    } finally {
      loading.value = false;
    }
  };

  watch(dialogVisible, (open) => {
    if (open) {
      nextTick(() => userFormRef.value?.clearValidate());
    }
  });

  return {
    dialogVisible,
    viewDialogVisible,
    dialogTitle,
    currentUserId,
    viewingUser,
    userFormRef,
    userForm,
    showClientForm,
    formRules,
    formatDate,
    handleUsernameBlur,
    handleRoleChange,
    handleAddUser,
    handleView,
    handleKeyDoubleClick,
    handleEdit,
    handleSaveUser,
  };
}
