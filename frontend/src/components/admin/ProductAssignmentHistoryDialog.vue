<template>
  <el-dialog
    v-model="visible"
    title="产品分配历史"
    width="800px"
    :close-on-click-modal="false"
    @close="handleClose"
    class="product-assignment-history-dialog"
  >
    <div v-loading="loading" class="assignment-history-content">
      <div v-if="assignments.length === 0 && !loading" class="empty-state">
        <el-empty description="暂无分配历史记录" />
      </div>
      
      <el-timeline v-else>
        <el-timeline-item
          v-for="(assignment, index) in assignments"
          :key="assignment.id"
          :timestamp="formatDateRange(assignment)"
          placement="top"
          :type="assignment.end_date ? 'success' : 'primary'"
        >
          <el-card class="assignment-card">
            <div class="assignment-header">
              <div class="client-info">
                <el-icon :size="20"><OfficeBuilding /></el-icon>
                <span class="client-name">{{ formatClientFullName(assignment) }}</span>
                <el-tag v-if="!assignment.end_date" type="success" size="small" class="current-tag">当前有效</el-tag>
              </div>
              <div class="action-buttons" v-if="!editingAssignments.has(assignment.id)">
                <el-button 
                  type="primary" 
                  size="small" 
                  :icon="Edit"
                  @click="handleEdit(assignment)"
                  circle
                  title="编辑日期"
                />
              </div>
            </div>
            <div class="assignment-details" v-if="!editingAssignments.has(assignment.id)">
              <div class="detail-item">
                <span class="label">客户ID:</span>
                <span class="value">{{ assignment.client_id }}</span>
              </div>
              <div class="detail-item">
                <span class="label">开始日期:</span>
                <span class="value">{{ formatDate(assignment.start_date) }}</span>
              </div>
              <div class="detail-item" v-if="assignment.end_date">
                <span class="label">结束日期:</span>
                <span class="value">{{ formatDate(assignment.end_date) }}</span>
              </div>
              <div class="detail-item" v-else>
                <span class="label">状态:</span>
                <span class="value success-text">进行中</span>
              </div>
            </div>
            <!-- 编辑模式 -->
            <div class="edit-form" v-else>
              <el-form :model="editForms[assignment.id]" label-width="100px" size="default">
                <el-form-item label="开始日期" required>
                  <el-date-picker
                    v-model="editForms[assignment.id].start_date"
                    type="date"
                    placeholder="选择开始日期"
                    format="YYYY-MM-DD"
                    value-format="YYYY-MM-DD"
                    style="width: 100%"
                  />
                </el-form-item>
                <el-form-item label="结束日期">
                  <el-date-picker
                    v-model="editForms[assignment.id].end_date"
                    type="date"
                    placeholder="选择结束日期（留空表示当前有效）"
                    format="YYYY-MM-DD"
                    value-format="YYYY-MM-DD"
                    :clearable="true"
                    style="width: 100%"
                  />
                  <div class="form-tip">留空表示当前有效</div>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="handleSave(assignment)" :loading="savingAssignments.has(assignment.id)">
                    保存
                  </el-button>
                  <el-button @click="handleCancelEdit(assignment.id)">取消</el-button>
                </el-form-item>
              </el-form>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </div>
    
    <template #footer>
      <div class="dialog-footer">
        <el-button type="primary" @click="handleClose">关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { OfficeBuilding, Edit } from '@element-plus/icons-vue';
import { getProductAssignments, updateAssignmentDates } from '../../api/product';

// 格式化客户全名（优先显示用户全名，如果没有则显示公司名称、联系人、电话）
const formatClientFullName = (assignment) => {
  if (!assignment) return '未知客户';
  
  // 优先显示用户全名
  if (assignment.user_full_name) {
    return assignment.user_full_name;
  }
  
  // 如果没有用户全名，显示公司名称、联系人、电话
  const parts = [];
  if (assignment.company_name) {
    parts.push(assignment.company_name);
  }
  if (assignment.contact_person) {
    parts.push(`(${assignment.contact_person})`);
  }
  if (assignment.phone) {
    parts.push(`- ${assignment.phone}`);
  }
  
  return parts.length > 0 ? parts.join(' ') : (assignment.client_name || '未知客户');
};

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  productId: {
    type: Number,
    default: null
  },
  productName: {
    type: String,
    default: ''
  }
});

const emit = defineEmits(['update:modelValue']);

const visible = ref(false);
const loading = ref(false);
const assignments = ref([]);
const editingAssignments = ref(new Set()); // 正在编辑的分配记录ID集合
const editForms = ref({}); // 编辑表单数据
const savingAssignments = ref(new Set()); // 正在保存的分配记录ID集合

watch(() => props.modelValue, (newVal) => {
  visible.value = newVal;
  if (newVal && props.productId) {
    fetchAssignments();
  }
});

watch(visible, (newVal) => {
  emit('update:modelValue', newVal);
});

const fetchAssignments = async () => {
  if (!props.productId) {
    ElMessage.warning('产品ID不能为空');
    return;
  }
  
  loading.value = true;
  try {
    const result = await getProductAssignments(props.productId);
    // 确保数据结构正确
    // API返回格式：{ code: 200, data: { data: [...], total: ... } }
    // 或者：{ code: 200, data: [...] }
    let assignmentsData = [];
    if (result && result.data) {
      if (Array.isArray(result.data)) {
        assignmentsData = result.data;
      } else if (result.data.data && Array.isArray(result.data.data)) {
        assignmentsData = result.data.data;
      } else if (result.data && Array.isArray(result.data)) {
        assignmentsData = result.data;
      }
    }
    assignments.value = assignmentsData;
    
    // 如果没有数据，显示提示
    if (assignments.value.length === 0) {
      // 不显示错误，因为可能是真的没有历史记录
    }
  } catch (error) {
    // 错误已在API中处理并显示消息
    assignments.value = [];
    
    // 如果是网络错误，提供重试建议
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout') || error.message?.includes('网络')) {
      ElMessage.warning('加载历史记录超时，请稍后重试');
    }
  } finally {
    loading.value = false;
  }
};

const formatDate = (dateStr) => {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  });
};

const formatDateRange = (assignment) => {
  if (assignment.end_date) {
    return `${formatDate(assignment.start_date)} - ${formatDate(assignment.end_date)}`;
  } else {
    return `${formatDate(assignment.start_date)} - 至今`;
  }
};

const handleClose = () => {
  visible.value = false;
  assignments.value = [];
  editingAssignments.value.clear();
  editForms.value = {};
  savingAssignments.value.clear();
};

const handleEdit = (assignment) => {
  // 进入编辑模式
  editingAssignments.value.add(assignment.id);
  editForms.value[assignment.id] = {
    start_date: assignment.start_date,
    end_date: assignment.end_date || null
  };
};

const handleCancelEdit = (assignmentId) => {
  // 取消编辑
  editingAssignments.value.delete(assignmentId);
  delete editForms.value[assignmentId];
};

const handleSave = async (assignment) => {
  const assignmentId = assignment.id;
  const formData = editForms.value[assignmentId];
  
  // 基本验证
  if (!formData.start_date) {
    ElMessage.warning('请选择开始日期');
    return;
  }
  
  // 日期比较：确保都是字符串格式进行比较
  const startDateStr = typeof formData.start_date === 'string' 
    ? formData.start_date 
    : (formData.start_date ? new Date(formData.start_date).toISOString().split('T')[0] : null);
  const endDateStr = formData.end_date 
    ? (typeof formData.end_date === 'string' 
        ? formData.end_date 
        : new Date(formData.end_date).toISOString().split('T')[0])
    : null;
  const originalStartDateStr = typeof assignment.start_date === 'string'
    ? assignment.start_date
    : (assignment.start_date ? new Date(assignment.start_date).toISOString().split('T')[0] : null);
  const originalEndDateStr = assignment.end_date
    ? (typeof assignment.end_date === 'string'
        ? assignment.end_date
        : new Date(assignment.end_date).toISOString().split('T')[0])
    : null;
  
  if (endDateStr && startDateStr > endDateStr) {
    ElMessage.warning('开始日期不能大于结束日期');
    return;
  }
  
  savingAssignments.value.add(assignmentId);
  
  try {
    // 构建更新数据（只发送有变化的字段）
    const updateData = {};
    if (startDateStr !== originalStartDateStr) {
      updateData.start_date = startDateStr;
    }
    // 对于end_date，需要明确处理：如果原值为null，新值也为null，则不更新
    // 如果原值和新值不同（包括null的变化），则需要更新
    const originalEndIsNull = !originalEndDateStr;
    const newEndIsNull = !endDateStr;
    
    if (originalEndIsNull !== newEndIsNull || (endDateStr && endDateStr !== originalEndDateStr)) {
      // end_date有变化，需要更新（明确设置为null或新值）
      updateData.end_date = endDateStr || null;
    }
    
    // 如果没有变化，直接退出编辑模式
    if (Object.keys(updateData).length === 0) {
      handleCancelEdit(assignmentId);
      ElMessage.info('没有检测到日期变化');
      return;
    }
    
    // 调用API更新
    await updateAssignmentDates(assignmentId, updateData);
    
    // 更新成功后，重新获取分配历史
    await fetchAssignments();
    
    ElMessage.success('日期更新成功，时间连贯性验证通过');
  } catch (error) {
    // 错误已在API中处理并显示消息
    console.error('更新分配历史日期失败:', error);
    
    // 如果是CSRF相关错误，提供更详细的提示
    if (error.response?.status === 403) {
      ElMessage.error('安全验证失败，请刷新页面后重试');
    } else if (error.message?.includes('CSRF') || error.message?.includes('csrf')) {
      ElMessage.error('安全验证失败，请刷新页面后重试');
    }
    // 其他错误已在 updateAssignmentDates 中处理
  } finally {
    savingAssignments.value.delete(assignmentId);
  }
};
</script>

<style scoped>
.product-assignment-history-dialog {
  --spacing-xs: 8px;
  --spacing-sm: 12px;
  --spacing-md: 16px;
  --spacing-lg: 20px;
  --spacing-xl: 24px;
}

.assignment-history-content {
  min-height: 200px;
  max-height: 600px;
  overflow-y: auto;
  padding: var(--spacing-md);
}

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}

.assignment-card {
  margin-bottom: var(--spacing-sm);
}

.assignment-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-sm);
}

.client-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.client-name {
  font-weight: 600;
  font-size: 16px;
  color: #303133;
}

.current-tag {
  margin-left: var(--spacing-xs);
}

.action-buttons {
  display: flex;
  gap: var(--spacing-xs);
}

.edit-form {
  margin-top: var(--spacing-md);
  padding: var(--spacing-md);
  background-color: #f5f7fa;
  border-radius: 4px;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.assignment-details {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-sm);
  margin-top: var(--spacing-sm);
}

.detail-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.label {
  color: #909399;
  font-size: 14px;
}

.value {
  color: #303133;
  font-size: 14px;
  font-weight: 500;
}

.success-text {
  color: #67c23a;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}

/* 移动端优化 */
@media (max-width: 767px) {
  .assignment-details {
    grid-template-columns: 1fr;
  }
  
  .assignment-history-content {
    max-height: 400px;
  }
}
</style>

