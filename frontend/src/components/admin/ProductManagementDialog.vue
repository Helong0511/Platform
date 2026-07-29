<!--
  产品管理弹窗（按客户维度）
  @file components/admin/ProductManagementDialog.vue
  说明：独立菜单页 ProductManagement.vue 为正式入口；本弹窗保留供兼容复用。
-->
<template>
  <el-dialog
    v-model="visible"
    :width="isMobile ? '95%' : (isTablet ? '90%' : '1400px')"
    :close-on-click-modal="false"
    @close="handleClose"
    class="product-management-dialog"
    :show-close="true"
    align-center
    :center="true"
    :append-to-body="true"
  >
    <template #header>
      <ProductDialogHeader :client-name="clientName" :product-count="products.length" />
    </template>

    <div class="product-management-content">
      <ProductActionBar :product-count="products.length" @add="handleAdd" />
      <ProductTable
        :products="products"
        :loading="loading"
        :is-mobile="isMobile"
        :table-max-height="tableMaxHeight"
        @history="handleViewHistory"
        @edit="handleEdit"
        @delete="handleDelete"
      />
    </div>

    <ProductAssignmentHistoryDialog
      v-model="assignmentHistoryVisible"
      :product-id="selectedProductForHistory?.id"
      :product-name="selectedProductForHistory?.name"
    />

    <ProductFormDialog
      ref="formDialogRef"
      v-model="formDialogVisible"
      :form-title="formTitle"
      :is-mobile="isMobile"
      :form-data="formData"
      :form-rules="formRules"
      :saving="saving"
      :product-names="productNames"
      :product-names-loading="productNamesLoading"
      :query-product-names="queryProductNames"
      @save="handleSave"
      @product-name-select="handleProductNameSelect"
      @product-name-blur="handleProductNameBlur"
      @load-product-names="loadProductNames"
    />

    <ProductTransferDateDialog
      v-model="transferDateDialogVisible"
      :transfer-date-form="transferDateForm"
      :product-assignments="productAssignments"
      :loading-assignments="loadingAssignments"
      :last-client-start-date="lastClientStartDate"
      :old-client-end-date="oldClientEndDate"
      :client-name="clientName"
      @start-date-change="handleStartDateChange"
      @end-date-change="handleEndDateChange"
      @confirm="confirmTransferDate"
    />
  </el-dialog>
</template>

<script setup>
import { ref, watch, computed, markRaw } from 'vue';
import { ElDialog, ElMessage, ElMessageBox } from 'element-plus';
import { Warning } from '@element-plus/icons-vue';
import { useDevice } from '../../composables/useDevice';
import { useProductForm } from '../../composables/useProductForm';
import ProductAssignmentHistoryDialog from './ProductAssignmentHistoryDialog.vue';
import ProductDialogHeader from './ProductDialogHeader.vue';
import ProductActionBar from './ProductActionBar.vue';
import ProductTable from './ProductTable.vue';
import ProductFormDialog from './ProductFormDialog.vue';
import ProductTransferDateDialog from './ProductTransferDateDialog.vue';
import '../../styles/product-management-dialog.css';

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  clientName: {
    type: String,
    default: '未知客户',
  },
  clientId: {
    type: Number,
    default: null,
  },
  products: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['update:modelValue', 'add', 'edit', 'delete', 'save', 'refresh']);

const { isMobile, isTablet } = useDevice();

const tableMaxHeight = computed(() => {
  if (isMobile.value) {
    const viewportHeight = window.innerHeight || 667;
    return Math.max(200, viewportHeight - 150);
  }
  if (isTablet.value) {
    const viewportHeight = window.innerHeight || 768;
    return Math.max(400, viewportHeight - 200);
  }
  const viewportHeight = window.innerHeight;
  return Math.max(400, viewportHeight - 260);
});

const visible = ref(props.modelValue);
const assignmentHistoryVisible = ref(false);
const selectedProductForHistory = ref(null);

const {
  formDialogRef,
  formDialogVisible,
  formTitle,
  saving,
  formData,
  formRules,
  productNames,
  productNamesLoading,
  queryProductNames,
  transferDateDialogVisible,
  transferDateForm,
  productAssignments,
  loadingAssignments,
  lastClientStartDate,
  oldClientEndDate,
  handleAdd,
  handleEdit,
  handleSave,
  handleProductNameSelect,
  handleProductNameBlur,
  loadProductNames,
  handleStartDateChange,
  handleEndDateChange,
  confirmTransferDate,
} = useProductForm(props, emit);

watch(() => props.modelValue, (val) => {
  visible.value = val;
});

watch(visible, (val) => {
  emit('update:modelValue', val);
});

const handleClose = () => {
  visible.value = false;
  emit('refresh');
};

const handleViewHistory = (product) => {
  if (product?.id) {
    selectedProductForHistory.value = product;
    assignmentHistoryVisible.value = true;
  } else {
    ElMessage.warning('无法查看历史记录：产品信息不完整');
  }
};

const handleDelete = async (id) => {
  try {
    await ElMessageBox.confirm(
      '确定要删除此产品吗？若产品仍有关联广告数据，将转移到「临时挂靠」并保留广告数据；无关联数据时会彻底删除。',
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
        icon: markRaw(Warning),
        appendTo: document.body,
        zIndex: 3001,
      },
    );
    emit('delete', id);
  } catch {
    // 用户取消
  }
};
</script>
