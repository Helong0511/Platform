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

    <el-card shadow="never" class="alias-card">
      <template #header>
        <div class="unrecognized-header">
          <div>
            <span class="unrecognized-title">英文别名映射</span>
            <span class="unrecognized-desc">上游非标准国名 → ISO 二字代码（如 U.S. Virgin Islands → VI）</span>
          </div>
          <div>
            <el-button type="primary" :icon="Plus" @click="openAliasDialog">新增别名</el-button>
            <el-button :icon="Refresh" :loading="aliasLoading" @click="fetchAliases">刷新</el-button>
          </div>
        </div>
      </template>
      <el-table v-loading="aliasLoading" :data="aliasList" border stripe size="small">
        <el-table-column prop="alias_name" label="别名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="alpha_2_code" label="映射代码" width="100" align="center">
          <template #default="{ row }">
            <el-tag type="success" size="small">{{ row.alpha_2_code }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="alias_normalized" label="规范化键" min-width="180" show-overflow-tooltip />
        <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleDeleteAlias(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="unrecognized-card">
      <template #header>
        <div class="unrecognized-header">
          <div>
            <span class="unrecognized-title">未识别国家代码</span>
            <span class="unrecognized-desc">来自广告数据 / TB 搜索数据 / 归档表，尚未在 countries 表登记</span>
          </div>
          <el-button :icon="Refresh" :loading="unrecognizedLoading" @click="fetchUnrecognized">
            刷新收集
          </el-button>
        </div>
      </template>

      <el-alert
        v-if="!unrecognizedLoading && unrecognizedList.length === 0"
        type="success"
        :closable="false"
        show-icon
        title="暂无未识别国家代码，业务数据中的代码均已在 countries 表登记。"
      />

      <el-table
        v-else
        v-loading="unrecognizedLoading"
        :data="unrecognizedList"
        border
        stripe
        size="small"
      >
        <el-table-column prop="country_code" label="国家代码" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_valid_alpha2 ? 'warning' : 'danger'" size="small">
              {{ row.country_code }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_count" label="出现次数" width="100" align="center" sortable />
        <el-table-column label="建议映射" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.suggested_alpha_2" type="success" size="small">{{ row.suggested_alpha_2 }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="别名" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.alias_registered ? 'success' : 'info'" size="small">
              {{ row.alias_registered ? '已登记' : '未登记' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数据来源" min-width="160">
          <template #default="{ row }">
            <el-tag
              v-for="source in row.sources"
              :key="source"
              size="small"
              type="info"
              style="margin-right: 6px;"
            >
              {{ sourceLabel(source) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="明细" min-width="240">
          <template #default="{ row }">
            <span v-if="row.ad_data_count">广告 {{ row.ad_data_count }}</span>
            <span v-if="row.tb_search_data_count">
              <template v-if="row.ad_data_count"> · </template>
              TB {{ row.tb_search_data_count }}
            </span>
            <span v-if="row.ad_data_archive_count">
              <template v-if="row.ad_data_count || row.tb_search_data_count"> · </template>
              归档 {{ row.ad_data_archive_count }}
            </span>
            <div v-if="row.variant_codes?.length > 1" class="variant-hint">
              含 {{ row.variant_codes.length }} 种写法
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.suggested_alpha_2"
              type="primary"
              link
              size="small"
              @click="handleQuickAddSuggested(row)"
            >
              添加 {{ row.suggested_alpha_2 }}
            </el-button>
            <el-tooltip
              v-else-if="!row.is_valid_alpha2"
              content="非标准二字代码，可先添加别名映射或修正业务数据"
              placement="top"
            >
              <el-button type="primary" link size="small" disabled>快速添加</el-button>
            </el-tooltip>
            <el-button
              v-else
              type="primary"
              link
              size="small"
              @click="handleQuickAdd(row)"
            >
              快速添加
            </el-button>
          </template>
        </el-table-column>
      </el-table>
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

    <el-dialog
      v-model="aliasDialogVisible"
      title="新增英文别名"
      :width="isMobile ? '95%' : '520px'"
      :close-on-click-modal="false"
      append-to-body
    >
      <el-form ref="aliasFormRef" :model="aliasForm" :rules="aliasFormRules" label-width="100px">
        <el-form-item label="别名" prop="alias_name">
          <el-input v-model="aliasForm.alias_name" placeholder="如 U.S. Virgin Islands" maxlength="150" />
        </el-form-item>
        <el-form-item label="映射代码" prop="alpha_2_code">
          <el-input v-model="aliasForm.alpha_2_code" maxlength="2" placeholder="如 VI" style="width: 120px;" />
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input v-model="aliasForm.remark" placeholder="可选" maxlength="255" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="aliasDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="aliasSubmitting" @click="submitAlias">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';
import {
  ElAlert,
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
  ElTag,
  ElTooltip
} from 'element-plus';
import { Plus, Refresh, Search } from '@element-plus/icons-vue';
import {
  getCountries,
  createCountry,
  updateCountry,
  deleteCountry,
  getUnrecognizedCountryCodes,
  getCountryAliases,
  createCountryAlias,
  deleteCountryAlias
} from '../../api/country';
import { useDevice } from '../../composables/useDevice';
import { logger } from '../../utils/logger';

const { isMobile } = useDevice();

const loading = ref(false);
const unrecognizedLoading = ref(false);
const aliasLoading = ref(false);
const aliasSubmitting = ref(false);
const submitting = ref(false);
const tableData = ref([]);
const unrecognizedList = ref([]);
const aliasList = ref([]);
const dialogVisible = ref(false);
const aliasDialogVisible = ref(false);
const editingId = ref(null);
const formRef = ref(null);
const aliasFormRef = ref(null);

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

const aliasForm = reactive({
  alias_name: '',
  alpha_2_code: '',
  remark: ''
});

const aliasFormRules = {
  alias_name: [{ required: true, message: '请输入别名', trigger: 'blur' }],
  alpha_2_code: [
    { required: true, message: '请输入映射代码', trigger: 'blur' },
    { pattern: /^[A-Za-z]{2}$/, message: '必须为 2 位字母', trigger: 'blur' }
  ]
};

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

const SOURCE_LABELS = {
  ad_data: '广告数据',
  tb_search_data: 'TB搜索数据',
  ad_data_archive: '广告归档'
};

const sourceLabel = (source) => SOURCE_LABELS[source] || source;

const fetchUnrecognized = async () => {
  unrecognizedLoading.value = true;
  try {
    const data = await getUnrecognizedCountryCodes();
    unrecognizedList.value = Array.isArray(data) ? data : [];
  } catch (error) {
    logger.error('收集未识别国家代码失败', error);
    ElMessage.error(error.message || '收集未识别国家代码失败');
  } finally {
    unrecognizedLoading.value = false;
  }
};

const fetchAliases = async () => {
  aliasLoading.value = true;
  try {
    const data = await getCountryAliases();
    aliasList.value = Array.isArray(data) ? data : [];
  } catch (error) {
    logger.error('获取国家别名失败', error);
    ElMessage.error(error.message || '获取国家别名失败');
  } finally {
    aliasLoading.value = false;
  }
};

const openAliasDialog = (preset = {}) => {
  aliasForm.alias_name = preset.alias_name || '';
  aliasForm.alpha_2_code = preset.alpha_2_code || '';
  aliasForm.remark = preset.remark || '';
  aliasDialogVisible.value = true;
  aliasFormRef.value?.clearValidate();
};

const submitAlias = async () => {
  if (!aliasFormRef.value) return;
  try {
    await aliasFormRef.value.validate();
  } catch {
    return;
  }
  aliasSubmitting.value = true;
  try {
    await createCountryAlias({
      alias_name: aliasForm.alias_name.trim(),
      alpha_2_code: aliasForm.alpha_2_code.trim().toUpperCase(),
      remark: aliasForm.remark?.trim() || null
    });
    ElMessage.success('别名创建成功');
    aliasDialogVisible.value = false;
    fetchAliases();
    fetchUnrecognized();
  } catch (error) {
    logger.error('创建别名失败', error);
    ElMessage.error(error.message || '创建别名失败');
  } finally {
    aliasSubmitting.value = false;
  }
};

const handleDeleteAlias = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除别名「${row.alias_name}」吗？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    });
    await deleteCountryAlias(row.id);
    ElMessage.success('删除成功');
    fetchAliases();
    fetchUnrecognized();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '删除失败');
    }
  }
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

const handleQuickAdd = (row) => {
  resetForm();
  formData.alpha_2_code = row.country_code.toUpperCase();
  dialogVisible.value = true;
};

const handleQuickAddSuggested = (row) => {
  resetForm();
  formData.alpha_2_code = row.suggested_alpha_2;
  formData.country_name_en = row.country_code;
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
    fetchUnrecognized();
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
  fetchUnrecognized();
  fetchAliases();
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
.alias-card,
.unrecognized-card,
.table-card {
  margin-bottom: 16px;
}

.variant-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.unrecognized-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.unrecognized-title {
  font-weight: 600;
  margin-right: 12px;
}

.unrecognized-desc {
  color: var(--el-text-color-secondary);
  font-size: 13px;
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
