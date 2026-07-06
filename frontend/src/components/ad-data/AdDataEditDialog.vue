<!--
  广告数据编辑对话框
  @file components/ad-data/AdDataEditDialog.vue
-->
<template>
  <el-dialog
    :model-value="visible"
    title="编辑广告数据"
    :width="isMobile ? '95%' : '600px'"
    :append-to-body="true"
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form
      ref="formRef"
      :model="editForm"
      :rules="editRules"
      :label-width="isMobile ? '0' : '140px'"
      class="edit-form"
    >
      <el-form-item label="数据日期" prop="date">
        <el-date-picker
          v-model="editForm.date"
          name="date"
          type="date"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          style="width: 100%;"
          disabled
        />
      </el-form-item>
      <el-form-item label="所属用户" prop="client_id">
        <el-select v-model="editForm.client_id" placeholder="选择用户" style="width: 100%;">
          <el-option
            v-for="user in users"
            :key="user.value"
            :label="user.label"
            :value="user.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="产品" prop="product_id">
        <el-select
          v-model="editForm.product_id"
          placeholder="选择产品"
          style="width: 100%;"
          :disabled="!editForm.client_id"
          @change="emit('product-change')"
        >
          <el-option
            v-for="product in products"
            :key="product.value"
            :label="product.label"
            :value="product.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="来源" prop="data_source">
        <el-select
          v-model="editForm.data_source"
          placeholder="选择或输入数据来源 slug"
          filterable
          allow-create
          default-first-option
          style="width: 100%;"
        >
          <el-option-group label="上游 API">
            <el-option
              v-for="item in upstreamSourceOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-option-group>
          <el-option-group label="其它">
            <el-option
              v-for="item in manualSourceOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-option-group>
        </el-select>
        <div class="form-tip">与库字段 data_source 一致，如 zhisuo / pomiad / addermobi / gam 等</div>
      </el-form-item>
      <el-form-item label="账号" prop="upstream_account">
        <el-input
          v-model="editForm.upstream_account"
          name="upstream_account"
          placeholder="上游账号，如 KE11、leadwin"
          clearable
          maxlength="64"
          show-word-limit
          style="width: 100%;"
        />
      </el-form-item>
      <el-form-item label="报表类型" prop="report_type">
        <el-select v-model="editForm.report_type" placeholder="选择报表类型" style="width: 100%;">
          <el-option-group label="统计维度">
            <el-option
              v-for="item in detailReportTypeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            >
              <span>{{ item.label }}</span>
              <span v-if="item.hint" class="option-hint">{{ item.hint }}</span>
            </el-option>
          </el-option-group>
          <el-option-group label="其它">
            <el-option
              v-for="item in otherReportTypeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            >
              <span>{{ item.label }}</span>
              <span v-if="item.hint" class="option-hint">{{ item.hint }}</span>
            </el-option>
          </el-option-group>
        </el-select>
        <div class="form-tip">
          unit=广告单元 / country=国家 / cross=交叉 / daily=日报；与列表筛选维度及唯一键一致
        </div>
      </el-form-item>
      <el-form-item label="广告单元" prop="ad_unit">
        <el-input
          v-model="editForm.ad_unit"
          name="ad_unit"
          placeholder="可选，留空表示无广告单元"
          clearable
          style="width: 100%;"
        />
      </el-form-item>
      <el-form-item label="国家" prop="country_code">
        <el-input
          v-model="editForm.country_code"
          name="country_code"
          placeholder="输入国家代码（如：US、USA、840、United States of America、美国）"
          style="width: 100%;"
        >
          <template #append>
            <el-button title="查看帮助" @click="emit('country-help')">?</el-button>
          </template>
        </el-input>
        <div class="form-tip">
          支持格式：二字母代码（US）、三字母代码（USA）、数字代码（840）、英文名称、中文名称
        </div>
      </el-form-item>
      <el-form-item label="请求数" prop="request_count">
        <el-input v-model.number="editForm.request_count" name="request_count" type="number" min="0" />
      </el-form-item>
      <el-form-item label="匹配数" prop="match_count">
        <el-input v-model.number="editForm.match_count" name="match_count" type="number" min="0" />
      </el-form-item>
      <el-form-item label="展示数" prop="display_count">
        <el-input v-model.number="editForm.display_count" name="display_count" type="number" min="0" />
      </el-form-item>
      <el-form-item label="点击数" prop="click_count">
        <el-input v-model.number="editForm.click_count" name="click_count" type="number" min="0" />
      </el-form-item>
      <el-form-item label="点击率" prop="click_rate">
        <el-input v-model.number="editForm.click_rate" name="click_rate" type="number" step="0.01" min="0" />
      </el-form-item>
      <el-form-item label="可见率" prop="viewability_rate">
        <el-input v-model.number="editForm.viewability_rate" name="viewability_rate" type="number" step="0.01" min="0" />
      </el-form-item>
      <el-form-item label="CPC" prop="cpc">
        <el-input v-model.number="editForm.cpc" name="cpc" type="number" step="0.01" min="0" />
      </el-form-item>
      <el-form-item label="PageViews" prop="pageviews">
        <el-input v-model.number="editForm.pageviews" name="pageviews" type="number" min="0" />
      </el-form-item>
      <el-form-item label="eCPM(扣)" prop="ecpm_after_deduct">
        <el-input v-model.number="editForm.ecpm_after_deduct" name="ecpm_after_deduct" type="number" step="0.01" min="0" />
      </el-form-item>
      <el-form-item label="eCPM" prop="ecpm_before_deduct">
        <el-input v-model.number="editForm.ecpm_before_deduct" name="ecpm_before_deduct" type="number" step="0.01" min="0" />
      </el-form-item>
      <el-form-item label="收益(扣)" prop="revenue_after_deduct">
        <el-input v-model.number="editForm.revenue_after_deduct" name="revenue_after_deduct" type="number" step="0.01" min="0" />
      </el-form-item>
      <el-form-item label="收益" prop="revenue_before_deduct">
        <el-input v-model.number="editForm.revenue_before_deduct" name="revenue_before_deduct" type="number" step="0.01" min="0" />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="emit('cancel')">取消</el-button>
        <el-button type="primary" @click="emit('save')">保存</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue';
import {
  AD_DATA_SOURCE_MANUAL_OPTIONS,
  UPSTREAM_API_DATA_SOURCES,
  buildAdDataSourceOptions,
  buildAdDataReportTypeOptions,
  AD_DATA_REPORT_TYPE_DETAIL_OPTIONS,
  AD_DATA_REPORT_TYPE_OTHER_OPTIONS
} from '../../constants/adDataDimension';

const props = defineProps({
  visible: { type: Boolean, default: false },
  editForm: { type: Object, required: true },
  editRules: { type: Object, default: () => ({}) },
  users: { type: Array, default: () => [] },
  products: { type: Array, default: () => [] },
  isMobile: { type: Boolean, default: false },
  reportTypeOptions: { type: Array, default: () => buildAdDataReportTypeOptions() },
});

const allReportTypeOptions = computed(() =>
  buildAdDataReportTypeOptions(props.editForm?.report_type)
);

const detailReportTypeOptions = computed(() =>
  allReportTypeOptions.value.filter((item) =>
    AD_DATA_REPORT_TYPE_DETAIL_OPTIONS.includes(item.value)
  )
);

const otherReportTypeOptions = computed(() =>
  allReportTypeOptions.value.filter((item) =>
    AD_DATA_REPORT_TYPE_OTHER_OPTIONS.includes(item.value) ||
    (!AD_DATA_REPORT_TYPE_DETAIL_OPTIONS.includes(item.value) &&
      !AD_DATA_REPORT_TYPE_OTHER_OPTIONS.includes(item.value))
  )
);

const allSourceOptions = computed(() =>
  buildAdDataSourceOptions(props.editForm?.data_source)
);

const upstreamSourceOptions = computed(() =>
  allSourceOptions.value.filter((item) => UPSTREAM_API_DATA_SOURCES.includes(item.value))
);

const manualSourceOptions = computed(() =>
  allSourceOptions.value.filter((item) => AD_DATA_SOURCE_MANUAL_OPTIONS.includes(item.value))
);

const emit = defineEmits(['update:visible', 'save', 'cancel', 'product-change', 'country-help']);

const formRef = ref(null);
defineExpose({ formRef });
</script>

<style scoped>
.form-tip {
  margin-top: 5px;
  font-size: 12px;
  color: #909399;
}

.option-hint {
  display: block;
  font-size: 11px;
  color: #a8abb2;
  line-height: 1.3;
}
</style>
