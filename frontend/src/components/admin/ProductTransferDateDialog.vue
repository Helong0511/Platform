<!--
  产品转移日期选择对话框
  @file components/admin/ProductTransferDateDialog.vue
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="选择产品转移日期"
    width="700px"
    :close-on-click-modal="false"
    class="product-transfer-date-dialog"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form :model="transferDateForm" label-width="120px">
      <el-form-item label="上一个客户">
        <el-input :value="formatClientFullName(transferDateForm.oldClientFullInfo)" disabled />
      </el-form-item>
      <el-form-item label="开始日期" required>
        <el-date-picker
          :model-value="transferDateForm.startDate"
          type="date"
          placeholder="选择开始日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          style="width: 100%;"
          :disabled-date="disabledStartDate"
          append-to-body
          :z-index="3002"
          @update:model-value="emit('start-date-change', $event)"
        />
        <div style="margin-top: 8px; color: #909399; font-size: 12px;">
          新客户开始拥有该产品的日期（修改后会自动更新旧客户结束日期）
          <template v-if="lastClientStartDate">
            ；不能早于当前有效分配开始日的次日（{{ formatDate(minNewClientStartDate) }}）
          </template>
        </div>
      </el-form-item>
      <el-form-item label="最后一个客户结束日期">
        <el-date-picker
          :model-value="transferDateForm.lastClientEndDate"
          type="date"
          placeholder="选择最后一个客户的结束日期（默认昨天）"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          style="width: 100%;"
          append-to-body
          :z-index="3002"
          :disabled-date="disabledEndDate"
          @update:model-value="emit('end-date-change', $event)"
        />
        <div style="margin-top: 8px; color: #909399; font-size: 12px;">
          上一个客户拥有该产品的结束日期（修改后会自动更新新客户开始日期，不能小于该客户的开始日期：{{ lastClientStartDate ? formatDate(lastClientStartDate) : '未设置' }}）
        </div>
      </el-form-item>
      <el-form-item v-if="productAssignments.length > 0" label="产品变更历史">
        <div v-loading="loadingAssignments" style="max-height: 300px; overflow-y: auto; padding: 12px; background: #f5f7fa; border-radius: 4px;">
          <el-timeline>
            <el-timeline-item
              v-for="assignment in productAssignments"
              :key="assignment.id"
              :timestamp="formatAssignmentDateRange(assignment)"
              placement="top"
              :type="assignment.end_date ? 'success' : 'primary'"
            >
              <div style="padding: 8px 0;">
                <div style="font-weight: bold; margin-bottom: 4px;">
                  {{ formatAssignmentClientFullName(assignment) }}
                  <el-tag v-if="!assignment.end_date" type="success" size="small" style="margin-left: 8px;">当前有效</el-tag>
                </div>
                <div style="font-size: 12px; color: #666;">
                  <div>开始日期：{{ formatDate(assignment.start_date) }}</div>
                  <div v-if="assignment.end_date">结束日期：{{ formatDate(assignment.end_date) }}</div>
                  <div v-else>状态：进行中</div>
                </div>
              </div>
            </el-timeline-item>
          </el-timeline>
        </div>
      </el-form-item>
      <el-form-item label="变更日期详情">
        <div style="padding: 12px; background: #f5f7fa; border-radius: 4px; line-height: 1.8;">
          <div style="margin-bottom: 8px;"><strong>上一个客户：</strong>{{ formatClientFullName(transferDateForm.oldClientFullInfo) }}</div>
          <div style="margin-bottom: 8px;"><strong>上一个客户结束日期：</strong>{{ oldClientEndDate || '未设置' }}</div>
          <div style="margin-bottom: 8px;"><strong>新客户：</strong>{{ clientName }}</div>
          <div><strong>新客户开始日期：</strong>{{ transferDateForm.startDate || '未设置' }}</div>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" :disabled="!transferDateForm.startDate" @click="emit('confirm')">确定</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import {
  ElButton,
  ElDatePicker,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElTag,
  ElTimeline,
  ElTimelineItem,
} from 'element-plus';
import { computed } from 'vue';
import { formatDate } from '../../utils/dateFormat';
import {
  formatAssignmentClientFullName,
  formatAssignmentDateRange,
  formatClientFullName,
} from '../../utils/productClientFormat';
import '../../styles/product-management-dialog.css';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  transferDateForm: { type: Object, required: true },
  productAssignments: { type: Array, default: () => [] },
  loadingAssignments: { type: Boolean, default: false },
  lastClientStartDate: { type: String, default: null },
  oldClientEndDate: { type: String, default: '' },
  clientName: { type: String, default: '' },
});

const emit = defineEmits(['update:modelValue', 'confirm', 'start-date-change', 'end-date-change']);

/** 将 YYYY-MM-DD 或 Date 规范为本地午夜，避免 UTC 解析偏移 */
function toLocalMidnight(value) {
  if (!value) return null;
  if (value instanceof Date) {
    const d = new Date(value);
    d.setHours(0, 0, 0, 0);
    return d;
  }
  const s = String(value).slice(0, 10);
  const parts = s.split('-').map(Number);
  if (parts.length !== 3 || parts.some((n) => Number.isNaN(n))) return null;
  const d = new Date(parts[0], parts[1] - 1, parts[2]);
  d.setHours(0, 0, 0, 0);
  return d;
}

function formatYmd(d) {
  if (!d) return '';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * 新客户最早可开始日 = 当前有效分配开始日 + 1 天
 * （旧客户结束日不能早于其开始日，故新客户开始日至少为其开始日次日）
 */
const minNewClientStartDate = computed(() => {
  const start = toLocalMidnight(props.lastClientStartDate);
  if (!start) return null;
  const next = new Date(start);
  next.setDate(next.getDate() + 1);
  return formatYmd(next);
});

function disabledStartDate(date) {
  const check = toLocalMidnight(date);
  if (!check) return true;
  const today = toLocalMidnight(new Date());
  if (check > today) return true;
  const minStart = toLocalMidnight(minNewClientStartDate.value);
  if (minStart && check < minStart) return true;
  return false;
}

function disabledEndDate(date) {
  const check = toLocalMidnight(date);
  if (!check) return true;
  const today = toLocalMidnight(new Date());
  if (check > today) return true;
  const start = toLocalMidnight(props.lastClientStartDate);
  if (start && check < start) return true;
  return false;
}
</script>
