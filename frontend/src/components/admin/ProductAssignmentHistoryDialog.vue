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
      <!-- 修改提示 -->
      <div v-if="pendingChanges.size > 0" class="pending-changes-alert">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
        >
          <template #title>
            <span>您有 {{ pendingChanges.size }} 条未保存的修改，请完成所有修改后点击"批量保存"按钮提交</span>
          </template>
        </el-alert>
      </div>
      
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
                <span class="value">
                  {{ formatDate(assignment.start_date) }}
                  <el-tag v-if="pendingChanges.has(assignment.id)" type="warning" size="small" style="margin-left: 8px;">
                    已修改
                  </el-tag>
                </span>
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
                  <el-button type="success" @click="handleTempSave(assignment)">
                    暂存修改
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
        <el-button 
          v-if="pendingChanges.size > 0"
          type="primary" 
          @click="handleBatchSave"
          :loading="batchSaving"
        >
          批量保存 ({{ pendingChanges.size }})
        </el-button>
        <el-button 
          v-if="pendingChanges.size > 0"
          @click="handleDiscardAll"
        >
          放弃所有修改
        </el-button>
        <el-button type="primary" @click="handleClose">关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue';
import { ElMessage, ElMessageBox, ElAlert } from 'element-plus';
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
const originalAssignments = ref([]); // 原始数据备份，用于验证
const editingAssignments = ref(new Set()); // 正在编辑的分配记录ID集合
const editForms = ref({}); // 编辑表单数据
const pendingChanges = ref(new Map()); // 暂存的修改 { assignmentId: { start_date, end_date, original } }
const batchSaving = ref(false); // 批量保存中

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
    // 保存原始数据备份（深拷贝）
    originalAssignments.value = JSON.parse(JSON.stringify(assignmentsData));
    
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
  // 如果有未保存的修改，提示用户
  if (pendingChanges.value.size > 0) {
    ElMessageBox.confirm(
      `您有 ${pendingChanges.value.size} 条未保存的修改，确定要关闭吗？未保存的修改将丢失。`,
      '确认关闭',
      {
        confirmButtonText: '确定关闭',
        cancelButtonText: '取消',
        type: 'warning'
      }
    ).then(() => {
      // 用户确认关闭，清除所有修改
      resetAllChanges();
      visible.value = false;
    }).catch(() => {
      // 用户取消关闭
    });
  } else {
    visible.value = false;
    resetAllChanges();
  }
};

// 重置所有修改
const resetAllChanges = () => {
  assignments.value = [];
  originalAssignments.value = [];
  editingAssignments.value.clear();
  editForms.value = {};
  pendingChanges.value.clear();
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

// 暂存修改（不提交到后端）
const handleTempSave = (assignment) => {
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
  
  if (endDateStr && startDateStr > endDateStr) {
    ElMessage.warning('开始日期不能大于结束日期');
    return;
  }
  
  // 获取原始数据
  const originalAssignment = originalAssignments.value.find(a => a.id === assignmentId);
  if (!originalAssignment) {
    ElMessage.error('找不到原始数据');
    return;
  }
  
  const originalStartDateStr = typeof originalAssignment.start_date === 'string'
    ? originalAssignment.start_date
    : (originalAssignment.start_date ? new Date(originalAssignment.start_date).toISOString().split('T')[0] : null);
  const originalEndDateStr = originalAssignment.end_date
    ? (typeof originalAssignment.end_date === 'string'
        ? originalAssignment.end_date
        : new Date(originalAssignment.end_date).toISOString().split('T')[0])
    : null;
  
  // 检查是否有变化
  const hasStartDateChange = startDateStr !== originalStartDateStr;
  const originalEndIsNull = !originalEndDateStr;
  const newEndIsNull = !endDateStr;
  const hasEndDateChange = originalEndIsNull !== newEndIsNull || (endDateStr && endDateStr !== originalEndDateStr);
  
  if (!hasStartDateChange && !hasEndDateChange) {
    handleCancelEdit(assignmentId);
    ElMessage.info('没有检测到日期变化');
    return;
  }
  
  // 暂存修改
  pendingChanges.value.set(assignmentId, {
    start_date: startDateStr,
    end_date: endDateStr,
    original: originalAssignment
  });
  
  // 更新显示的数据（用于预览）
  const assignmentIndex = assignments.value.findIndex(a => a.id === assignmentId);
  if (assignmentIndex !== -1) {
    assignments.value[assignmentIndex] = {
      ...assignments.value[assignmentIndex],
      start_date: startDateStr,
      end_date: endDateStr
    };
  }
  
  // 退出编辑模式
  handleCancelEdit(assignmentId);
  
  ElMessage.success('修改已暂存，请完成所有修改后点击"批量保存"提交');
};

// 验证所有暂存的修改
const validateAllChanges = () => {
  const errors = [];
  const changes = Array.from(pendingChanges.value.entries());
  
  if (changes.length === 0) {
    return { valid: true, errors: [] };
  }
  
  // 构建修改后的完整数据（用于验证）
  const modifiedAssignments = assignments.value.map(assignment => {
    const change = pendingChanges.value.get(assignment.id);
    if (change) {
      return {
        ...assignment,
        start_date: change.start_date,
        end_date: change.end_date
      };
    }
    return assignment;
  });
  
  // 按开始日期排序
  const sortedAssignments = [...modifiedAssignments].sort((a, b) => {
    const dateA = new Date(a.start_date);
    const dateB = new Date(b.start_date);
    return dateA - dateB;
  });
  
  // 验证1: 检查每个记录的基本逻辑
  for (const assignment of sortedAssignments) {
    if (assignment.end_date && assignment.start_date > assignment.end_date) {
      errors.push(`记录ID ${assignment.id}: 开始日期（${assignment.start_date}）不能大于结束日期（${assignment.end_date}）`);
    }
  }
  
  // 验证2: 检查重叠
  for (let i = 0; i < sortedAssignments.length; i++) {
    for (let j = i + 1; j < sortedAssignments.length; j++) {
      const a1 = sortedAssignments[i];
      const a2 = sortedAssignments[j];
      
      const a1End = a1.end_date || '9999-12-31';
      const a2End = a2.end_date || '9999-12-31';
      
      // 检查是否重叠：A.start <= B.end AND A.end >= B.start
      if (a1.start_date <= a2End && a1End >= a2.start_date) {
        errors.push(
          `记录ID ${a1.id} (${a1.start_date} 至 ${a1.end_date || '当前有效'}) ` +
          `与记录ID ${a2.id} (${a2.start_date} 至 ${a2.end_date || '当前有效'}) 重叠`
        );
      }
    }
  }
  
  // 验证3: 检查空窗期
  for (let i = 0; i < sortedAssignments.length - 1; i++) {
    const current = sortedAssignments[i];
    const next = sortedAssignments[i + 1];
    
    if (current.end_date) {
      // 计算期望的下一个开始日期（当前结束日期 + 1天）
      const currentEnd = new Date(current.end_date);
      currentEnd.setDate(currentEnd.getDate() + 1);
      const expectedNextStart = currentEnd.toISOString().split('T')[0];
      
      if (next.start_date !== expectedNextStart) {
        const gapDays = Math.floor((new Date(next.start_date) - new Date(current.end_date)) / (1000 * 60 * 60 * 24));
        if (gapDays > 1) {
          errors.push(
            `记录ID ${current.id} (结束日期: ${current.end_date}) ` +
            `与记录ID ${next.id} (开始日期: ${next.start_date}) ` +
            `之间存在 ${gapDays - 1} 天的空窗期`
          );
        } else if (gapDays < 1) {
          errors.push(
            `记录ID ${current.id} (结束日期: ${current.end_date}) ` +
            `与记录ID ${next.id} (开始日期: ${next.start_date}) 重叠`
          );
        }
      }
    }
  }
  
  // 验证4: 检查是否有多个当前有效的记录
  const activeAssignments = sortedAssignments.filter(a => !a.end_date);
  if (activeAssignments.length > 1) {
    const activeIds = activeAssignments.map(a => a.id).join(', ');
    errors.push(`有 ${activeAssignments.length} 个当前有效的分配记录 (记录ID: ${activeIds})，应该只有一个`);
  }
  
  return {
    valid: errors.length === 0,
    errors
  };
};

// 批量保存所有修改
const handleBatchSave = async () => {
  if (pendingChanges.value.size === 0) {
    ElMessage.info('没有需要保存的修改');
    return;
  }
  
  // 先进行验证
  const validation = validateAllChanges();
  if (!validation.valid) {
    ElMessageBox.alert(
      `验证失败，发现以下问题：\n\n${validation.errors.join('\n')}\n\n请修正后重试。`,
      '验证失败',
      {
        type: 'error',
        confirmButtonText: '确定'
      }
    );
    return;
  }
  
  // 确认保存
  try {
    await ElMessageBox.confirm(
      `确定要保存 ${pendingChanges.value.size} 条修改吗？保存后将进行完整的时间连贯性验证。`,
      '确认保存',
      {
        confirmButtonText: '确定保存',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
  } catch {
    // 用户取消
    return;
  }
  
  batchSaving.value = true;
  
  try {
    // 按顺序提交所有修改
    const changes = Array.from(pendingChanges.value.entries());
    let successCount = 0;
    let failCount = 0;
    const errors = [];
    
    for (const [assignmentId, change] of changes) {
      try {
        // 构建更新数据
        const updateData = {};
        const original = change.original;
        
        const originalStartDateStr = typeof original.start_date === 'string'
          ? original.start_date
          : (original.start_date ? new Date(original.start_date).toISOString().split('T')[0] : null);
        const originalEndDateStr = original.end_date
          ? (typeof original.end_date === 'string'
              ? original.end_date
              : new Date(original.end_date).toISOString().split('T')[0])
          : null;
        
        if (change.start_date !== originalStartDateStr) {
          updateData.start_date = change.start_date;
        }
        
        const originalEndIsNull = !originalEndDateStr;
        const newEndIsNull = !change.end_date;
        if (originalEndIsNull !== newEndIsNull || (change.end_date && change.end_date !== originalEndDateStr)) {
          updateData.end_date = change.end_date || null;
        }
        
        // 调用API更新
        await updateAssignmentDates(assignmentId, updateData);
        successCount++;
      } catch (error) {
        failCount++;
        const errorMsg = error.response?.data?.detail || error.message || '更新失败';
        errors.push(`记录ID ${assignmentId}: ${errorMsg}`);
        console.error(`更新分配记录 ${assignmentId} 失败:`, error);
      }
    }
    
    if (failCount > 0) {
      ElMessageBox.alert(
        `部分更新失败：\n\n${errors.join('\n')}\n\n已成功更新 ${successCount} 条，失败 ${failCount} 条。`,
        '部分更新失败',
        {
          type: 'warning',
          confirmButtonText: '确定'
        }
      );
    } else {
      ElMessage.success(`成功保存 ${successCount} 条修改，时间连贯性验证通过`);
    }
    
    // 重新获取分配历史
    await fetchAssignments();
    
    // 清除所有暂存的修改
    pendingChanges.value.clear();
  } catch (error) {
    console.error('批量保存失败:', error);
    ElMessage.error('批量保存失败，请稍后重试');
  } finally {
    batchSaving.value = false;
  }
};

// 放弃所有修改
const handleDiscardAll = async () => {
  if (pendingChanges.value.size === 0) {
    ElMessage.info('没有需要放弃的修改');
    return;
  }
  
  try {
    await ElMessageBox.confirm(
      `确定要放弃所有 ${pendingChanges.value.size} 条未保存的修改吗？此操作不可恢复。`,
      '确认放弃',
      {
        confirmButtonText: '确定放弃',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    
    // 恢复原始数据
    assignments.value = JSON.parse(JSON.stringify(originalAssignments.value));
    pendingChanges.value.clear();
    editingAssignments.value.clear();
    editForms.value = {};
    
    ElMessage.success('已放弃所有修改');
  } catch {
    // 用户取消
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

.pending-changes-alert {
  margin-bottom: var(--spacing-md);
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

