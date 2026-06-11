<!--
  管理端 - 国家与国家代码维护
  @file views/admin/CountryManagement.vue
-->
<template>
  <div class="country-management">
    <div class="page-header">
      <div class="header-left">
        <h2>国家维护</h2>
        <p class="page-description">维护 ISO 3166-1 国家名称与国家代码（对应 countries 表）</p>
      </div>
      <div class="header-right">
        <el-button type="primary" :icon="Plus" @click="handleCreate">新增国家</el-button>
      </div>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="关键字">
          <el-input
            v-model="searchForm.keyword"
            placeholder="国家名称或代码"
            clearable
            style="width: 220px;"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon :size="16"><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="大洲">
          <el-input
            v-model="searchForm.continent"
            placeholder="所属大洲"
            clearable
            style="width: 160px;"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" :loading="loading" @click="handleSearch">查询</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table v-loading="loading" :data="tableData" border stripe>
        <el-table-column prop="alpha_2_code" label="国家代码" width="110" align="center">
          <template #default="{ row }">
            <el-tag type="primary" size="small">{{ row.alpha_2_code }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="country_name_zh" label="国家（中文）" min-width="140" show-overflow-tooltip />
        <el-table-column prop="country_name_en" label="国家（英文）" min-width="160" show-overflow-tooltip />
        <el-table-column prop="alpha_3_code" label="三字代码" width="100" align="center" />
        <el-table-column prop="numeric_code" label="数字代码" width="100" align="center" />
        <el-table-column prop="continent" label="大洲" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.continent || '-' }}</template>
        </el-table-column>
        <el-table-column prop="subregion" label="地区" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.subregion || '-' }}</template>
        </el-table-column>
        <el-table-column prop="independent_status" label="独立国家" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.independent_status ? 'success' : 'info'" size="small">
              {{ row.independent_status ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchList"
          @current-change="fetchList"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑国家' : '新增国家'"
      :width="isMobile ? '95%' : '680px'"
      :close-on-click-modal="false"
      append-to-body
    >
      <el-form ref="formRef" :model="formData" :rules="formRules" label-width="120px">
        <el-form-item label="国家代码" prop="alpha_2_code">
          <el-input
            v-model="formData.alpha_2_code"
            maxlength="2"
            placeholder="二字代码，如 CN、US"
            style="width: 200px;"
          />
        </el-form-item>
        <el-form-item label="国家（中文）" prop="country_name_zh">
          <el-input v-model="formData.country_name_zh" placeholder="如：中国" maxlength="100" />
        </el-form-item>
        <el-form-item label="国家（英文）" prop="country_name_en">
          <el-input v-model="formData.country_name_en" placeholder="如：China" maxlength="100" />
        </el-form-item>
        <el-form-item label="三字代码" prop="alpha_3_code">
          <el-input
            v-model="formData.alpha_3_code"
            maxlength="3"
            placeholder="如：CHN"
            style="width: 200px;"
          />
        </el-form-item>
        <el-form-item label="数字代码" prop="numeric_code">
          <el-input
            v-model="formData.numeric_code"
            maxlength="3"
            placeholder="如：156"
            style="width: 200px;"
          />
        </el-form-item>
        <el-form-item label="官方中文名" prop="official_name_zh">
          <el-input v-model="formData.official_name_zh" placeholder="可选" maxlength="150" />
        </el-form-item>
        <el-form-item label="官方英文名" prop="official_name_en">
          <el-input v-model="formData.official_name_en" placeholder="可选" maxlength="150" />
        </el-form-item>
        <el-form-item label="所属大洲" prop="continent">
          <el-input v-model="formData.continent" placeholder="如：亚洲" maxlength="50" />
        </el-form-item>
        <el-form-item label="所属地区" prop="subregion">
          <el-input v-model="formData.subregion" placeholder="如：东亚" maxlength="50" />
        </el-form-item>
        <el-form-item label="独立国家" prop="independent_status">
          <el-switch v-model="formData.independent_status" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';
import {
  ElButton,
  ElCard,
  ElDialog,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElPagination,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag
} from 'element-plus';
import { Plus, Refresh, Search } from '@element-plus/icons-vue';
import { getCountries, createCountry, updateCountry, deleteCountry } from '../../api/country';
import { useDevice } from '../../composables/useDevice';
import { logger } from '../../utils/logger';

const { isMobile } = useDevice();

const loading = ref(false);
const submitting = ref(false);
const tableData = ref([]);
const dialogVisible = ref(false);
const editingId = ref(null);
const formRef = ref(null);

const searchForm = reactive({
  keyword: '',
  continent: ''
});

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
});

const defaultFormData = () => ({
  alpha_2_code: '',
  alpha_3_code: '',
  numeric_code: '',
  country_name_zh: '',
  country_name_en: '',
  official_name_zh: '',
  official_name_en: '',
  independent_status: true,
  continent: '',
  subregion: ''
});

const formData = reactive(defaultFormData());

const formRules = {
  alpha_2_code: [
    { required: true, message: '请输入国家二字代码', trigger: 'blur' },
    { pattern: /^[A-Za-z]{2}$/, message: '必须为 2 位字母', trigger: 'blur' }
  ],
  alpha_3_code: [
    { required: true, message: '请输入国家三字代码', trigger: 'blur' },
    { pattern: /^[A-Za-z]{3}$/, message: '必须为 3 位字母', trigger: 'blur' }
  ],
  numeric_code: [
    { required: true, message: '请输入国家数字代码', trigger: 'blur' },
    { pattern: /^\d{3}$/, message: '必须为 3 位数字', trigger: 'blur' }
  ],
  country_name_zh: [{ required: true, message: '请输入国家中文名称', trigger: 'blur' }],
  country_name_en: [{ required: true, message: '请输入国家英文名称', trigger: 'blur' }]
};

const resetForm = () => {
  Object.assign(formData, defaultFormData());
  editingId.value = null;
  formRef.value?.clearValidate();
};

const fetchList = async () => {
  loading.value = true;
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize
    };
    if (searchForm.keyword?.trim()) {
      params.keyword = searchForm.keyword.trim();
    }
    if (searchForm.continent?.trim()) {
      params.continent = searchForm.continent.trim();
    }
    const result = await getCountries(params);
    tableData.value = result.data || [];
    pagination.total = result.total || 0;
  } catch (error) {
    logger.error('获取国家列表失败', error);
    ElMessage.error(error.message || '获取国家列表失败');
  } finally {
    loading.value = false;
  }
};

const handleSearch = () => {
  pagination.page = 1;
  fetchList();
};

const handleReset = () => {
  searchForm.keyword = '';
  searchForm.continent = '';
  pagination.page = 1;
  fetchList();
};

const handleCreate = () => {
  resetForm();
  dialogVisible.value = true;
};

const handleEdit = (row) => {
  resetForm();
  editingId.value = row.id;
  Object.assign(formData, {
    alpha_2_code: row.alpha_2_code,
    alpha_3_code: row.alpha_3_code,
    numeric_code: row.numeric_code,
    country_name_zh: row.country_name_zh,
    country_name_en: row.country_name_en,
    official_name_zh: row.official_name_zh || '',
    official_name_en: row.official_name_en || '',
    independent_status: row.independent_status !== false,
    continent: row.continent || '',
    subregion: row.subregion || ''
  });
  dialogVisible.value = true;
};

const buildPayload = () => ({
  alpha_2_code: formData.alpha_2_code.trim().toUpperCase(),
  alpha_3_code: formData.alpha_3_code.trim().toUpperCase(),
  numeric_code: formData.numeric_code.trim(),
  country_name_zh: formData.country_name_zh.trim(),
  country_name_en: formData.country_name_en.trim(),
  official_name_zh: formData.official_name_zh?.trim() || null,
  official_name_en: formData.official_name_en?.trim() || null,
  independent_status: formData.independent_status,
  continent: formData.continent?.trim() || null,
  subregion: formData.subregion?.trim() || null
});

const handleSubmit = async () => {
  if (!formRef.value) return;
  try {
    await formRef.value.validate();
  } catch {
    return;
  }

  submitting.value = true;
  try {
    const payload = buildPayload();
    if (editingId.value) {
      await updateCountry(editingId.value, payload);
      ElMessage.success('更新成功');
    } else {
      await createCountry(payload);
      ElMessage.success('创建成功');
    }
    dialogVisible.value = false;
    fetchList();
  } catch (error) {
    logger.error('保存国家失败', error);
    ElMessage.error(error.message || '保存失败');
  } finally {
    submitting.value = false;
  }
};

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定删除国家「${row.country_name_zh}（${row.alpha_2_code}）」吗？`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    );
    await deleteCountry(row.id);
    ElMessage.success('删除成功');
    if (tableData.value.length === 1 && pagination.page > 1) {
      pagination.page -= 1;
    }
    fetchList();
  } catch (error) {
    if (error !== 'cancel') {
      logger.error('删除国家失败', error);
      ElMessage.error(error.message || '删除失败');
    }
  }
};

onMounted(() => {
  fetchList();
});
</script>

<style scoped>
.country-management {
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
  gap: 16px;
}

.page-header h2 {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
}

.page-description {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.filter-card,
.table-card {
  margin-bottom: 16px;
}

.pagination-container {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
  }
}
</style>
